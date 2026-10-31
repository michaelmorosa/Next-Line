from django.contrib import admin, messages

from rides.analysis import haversine

from .models import Feature, FeatureProgress, Trail
from .sharing import merge_feature, promote

# "Merge into nearest" looks this far for an approved feature on the same trail.
MERGE_SEARCH_M = 40


class FeatureInline(admin.TabularInline):
    model = Feature
    extra = 0
    fields = ('name', 'kind', 'lat', 'lng', 'created_by', 'approved')
    raw_id_fields = ('created_by',)


@admin.register(Trail)
class TrailAdmin(admin.ModelAdmin):
    list_display = ('name', 'direction', 'difficulty', 'owner', 'is_auto', 'length_m', 'drop_m', 'created_at')
    list_filter = ('direction', 'difficulty', 'is_auto')
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
                f"existing ones. {r['features_pending']} riders' features are waiting for approval under Features."
            ), messages.SUCCESS)


@admin.register(Feature)
class FeatureAdmin(admin.ModelAdmin):
    """Approve riders' pins on shared trails. Delete a pin to reject it."""
    list_display = ('name', 'trail', 'kind', 'created_by', 'approved', 'created_at')
    list_filter = ('approved', 'kind')
    search_fields = ('name', 'trail__name', 'created_by__username')
    raw_id_fields = ('trail', 'created_by')
    actions = ['approve', 'merge_into_nearest']

    @admin.action(description='Approve: show to everyone and count toward rider level')
    def approve(self, request, queryset):
        count = queryset.update(approved=True)
        self.message_user(request, f'Approved {count} feature(s).', messages.SUCCESS)

    @admin.action(description='Duplicate: merge into the nearest approved feature on the same trail')
    def merge_into_nearest(self, request, queryset):
        for feature in queryset:
            candidates = Feature.objects.filter(trail=feature.trail, approved=True).exclude(pk=feature.pk)
            nearest = min(candidates, key=lambda f: haversine(f.lat, f.lng, feature.lat, feature.lng), default=None)
            if not nearest or haversine(nearest.lat, nearest.lng, feature.lat, feature.lng) > MERGE_SEARCH_M:
                self.message_user(request, f'No approved feature within {MERGE_SEARCH_M} m of {feature.name}.',
                                  messages.WARNING)
                continue
            merge_feature(feature, nearest)
            self.message_user(request, f'Merged {feature.name} into {nearest.name}.', messages.SUCCESS)


@admin.register(FeatureProgress)
class FeatureProgressAdmin(admin.ModelAdmin):
    list_display = ('user', 'feature', 'status', 'clean_count', 'first_cleaned_at')
    list_filter = ('status',)
    raw_id_fields = ('user', 'feature')
