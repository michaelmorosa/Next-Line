from django.contrib import admin, messages

from rides.analysis import haversine

from .models import (
    Feature, FeatureLog, FeatureMedia, FeatureProgress, FeatureReport, GradingGuidelines, Trail, TrailSystem,
)
from .sharing import merge_feature, promote

# "Merge into nearest" looks this far for another feature on the same trail.
MERGE_SEARCH_M = 40


@admin.register(TrailSystem)
class TrailSystemAdmin(admin.ModelAdmin):
    list_display = ('name', 'location', 'is_demo')
    prepopulated_fields = {'slug': ('name',)}


class FeatureInline(admin.TabularInline):
    model = Feature
    extra = 0
    fields = ('position', 'name', 'type', 'grade', 'status')
    show_change_link = True


@admin.register(Trail)
class TrailAdmin(admin.ModelAdmin):
    list_display = ('name', 'system', 'direction', 'difficulty', 'owner', 'is_auto', 'length_m', 'drop_m')
    list_filter = ('system', 'direction', 'difficulty', 'is_auto')
    search_fields = ('name', 'owner__username')
    raw_id_fields = ('owner',)
    inlines = [FeatureInline]
    actions = ['make_shared']

    @admin.action(description="Make shared, merging riders' copies of it")
    def make_shared(self, request, queryset):
        for trail in queryset:
            if trail.owner_id is None:
                self.message_user(request, f'{trail.name} is already shared.', messages.WARNING)
                continue
            r = promote(trail)
            self.message_user(request, (
                f"{trail.name} is now shared. Merged {r['copies']} copies from {r['riders']} rider(s): "
                f"{r['laps']} laps moved, {r['features_moved']} features moved, {r['features_merged']} merged into "
                f"existing ones. Moved features are drafts until the trail team grades and certifies them."
            ), messages.SUCCESS)


class FeatureMediaInline(admin.TabularInline):
    model = FeatureMedia
    extra = 0
    fields = ('kind', 'file', 'caption', 'position')


@admin.register(Feature)
class FeatureAdmin(admin.ModelAdmin):
    list_display = ('name', 'trail', 'type', 'grade', 'status', 'last_verified_at', 'created_by')
    list_filter = ('status', 'type', 'trail__system')
    search_fields = ('name', 'trail__name')
    raw_id_fields = ('trail', 'created_by', 'submitted_by', 'certified_by')
    inlines = [FeatureMediaInline]
    actions = ['merge_into_nearest']

    @admin.action(description='Duplicate: merge into the nearest other feature on the same trail')
    def merge_into_nearest(self, request, queryset):
        for feature in queryset:
            candidates = Feature.objects.filter(trail=feature.trail).exclude(pk__in=queryset)
            nearest = min(candidates, key=lambda f: haversine(f.lat, f.lng, feature.lat, feature.lng), default=None)
            if not nearest or haversine(nearest.lat, nearest.lng, feature.lat, feature.lng) > MERGE_SEARCH_M:
                self.message_user(request, f'No other feature within {MERGE_SEARCH_M} m of {feature.name}.',
                                  messages.WARNING)
                continue
            merge_feature(feature, nearest)
            self.message_user(request, f'Merged {feature.name} into {nearest.name}.', messages.SUCCESS)


@admin.register(FeatureLog)
class FeatureLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'feature', 'outcome', 'ridden_on', 'grade_at_log')
    list_filter = ('outcome',)
    raw_id_fields = ('user', 'feature', 'ride')


@admin.register(FeatureReport)
class FeatureReportAdmin(admin.ModelAdmin):
    list_display = ('feature', 'user', 'status', 'note', 'created_at')
    list_filter = ('status',)
    raw_id_fields = ('feature', 'user', 'resolved_by')


@admin.register(GradingGuidelines)
class GradingGuidelinesAdmin(admin.ModelAdmin):
    fields = ('body', 'updated_at', 'updated_by')
    readonly_fields = ('updated_at', 'updated_by')

    def has_add_permission(self, request):
        return not GradingGuidelines.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(FeatureProgress)
class FeatureProgressAdmin(admin.ModelAdmin):
    """Legacy, read-only: progress from before rider logs."""
    list_display = ('user', 'feature', 'status', 'clean_count', 'first_cleaned_at')
    raw_id_fields = ('user', 'feature')

    def has_change_permission(self, request, obj=None):
        return False
