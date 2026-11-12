from django import forms
from django.contrib import admin, messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html, linebreaks

from progression import content
from rides.analysis import haversine

from . import certification, share
from .models import (
    Certification, Feature, FeatureLog, FeatureMedia, FeatureReport, GradingGuidelines,
    ReportStatus, Trail, TrailSystem,
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
    readonly_fields = ('status',)
    show_change_link = True


@admin.register(Trail)
class TrailAdmin(admin.ModelAdmin):
    list_display = ('name', 'system', 'direction', 'difficulty', 'owner', 'is_auto', 'length_m', 'features_link')
    list_filter = ('system', 'direction', 'difficulty', 'is_auto')
    search_fields = ('name', 'owner__username')
    raw_id_fields = ('owner',)
    inlines = [FeatureInline]
    actions = ['make_shared']

    @admin.display(description='Features')
    def features_link(self, trail):
        if trail.owner_id:
            return '-'
        url = reverse('admin:trails_trail_features', args=[trail.pk])
        return format_html('<a href="{}">Order and ladders ({})</a>', url, trail.features.count())

    def get_urls(self):
        return [
            path('<int:trail_id>/features/', self.admin_site.admin_view(self.features_view),
                 name='trails_trail_features'),
        ] + super().get_urls()

    def features_view(self, request, trail_id):
        """Bulk view of one trail: features in riding order (move them up and down) and the trail system's ladders,
        with warnings where grades don't step up one at a time."""
        trail = get_object_or_404(Trail, pk=trail_id, owner__isnull=True)
        features = list(trail.features.order_by('position', 'id'))
        if request.method == 'POST' and request.POST.get('move'):
            feature_id, direction = request.POST['move'].split(':')
            ids = [f.id for f in features]
            i = ids.index(int(feature_id))
            j = i - 1 if direction == 'up' else i + 1
            if 0 <= j < len(ids):
                ids[i], ids[j] = ids[j], ids[i]
                certification.renumber(trail, ids)
            return redirect(request.path)
        ladders = {}
        if trail.system_id:
            in_system = Feature.objects.filter(trail__system=trail.system_id, trail__owner__isnull=True).exclude(
                status=Certification.CLOSED).select_related('trail').order_by('type', 'grade', 'trail__name')
            for f in in_system:
                ladders.setdefault(f.get_type_display(), []).append(f)
        warnings = certification.ladder_warnings(trail.system, None) if trail.system_id else \
            certification.ladder_warnings(None, features)
        context = {
            **self.admin_site.each_context(request),
            'title': f'{trail.name}: features',
            'trail': trail,
            'features': [
                {'feature': f, 'stale': certification.is_stale(f),
                 'change_url': reverse('admin:trails_feature_change', args=[f.pk])}
                for f in features
            ],
            'ladders': sorted(ladders.items()),
            'warnings': warnings,
            'opts': self.model._meta,
        }
        return TemplateResponse(request, 'admin/trails/trail_features.html', context)

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
    """Upload the POV clip here from a computer. Photos added here aren't resized; the app's capture is."""
    model = FeatureMedia
    extra = 1
    fields = ('kind', 'file', 'caption', 'position')


def skill_choices():
    return [(s['id'], s['name']) for s in sorted(content.skill_tree()['skills'], key=lambda s: s['name'])]


class FeatureForm(forms.ModelForm):
    skill_tags = forms.MultipleChoiceField(
        choices=skill_choices, required=False, widget=forms.CheckboxSelectMultiple,
        help_text='Skills this feature uses. Their tips and drills show under "Stuck?", and they count toward the '
                  "rider's strengths.",
    )

    class Meta:
        model = Feature
        fields = '__all__'


@admin.register(Feature)
class FeatureAdmin(admin.ModelAdmin):
    form = FeatureForm
    list_display = ('name', 'trail', 'type', 'grade', 'status', 'submitted_at', 'last_verified_at', 'stale')
    list_filter = ('status', 'type', 'trail__system', 'trail')
    search_fields = ('name', 'trail__name')
    raw_id_fields = ('trail', 'created_by', 'submitted_by', 'certified_by')
    readonly_fields = ('status', 'submitted_by', 'submitted_at', 'certified_by', 'certified_at', 'last_verified_at',
                       'created_by', 'grading_guidelines')
    inlines = [FeatureMediaInline]
    actions = ['submit', 'certify', 'flag_changed', 'flag_closed', 'reopen', 'verify', 'feature_of_the_week',
               'merge_into_nearest']
    fieldsets = (
        (None, {'fields': ('trail', 'name', 'type', 'grade', 'position', 'lat', 'lng')}),
        ('Measurements', {'fields': ('drop_height_m', 'gap_length_m', 'steepness_deg')}),
        ('For riders', {'fields': ('description', 'how_to_ride', 'what_can_go_wrong', 'has_ride_around',
                                   'ride_around_grade', 'ride_around_note', 'skill_tags')}),
        ('Certification', {'fields': ('status', 'created_by', 'submitted_by', 'submitted_at', 'certified_by',
                                      'certified_at', 'last_verified_at')}),
        ('Grading guidelines', {'fields': ('grading_guidelines',), 'classes': ('collapse',)}),
    )

    @admin.display(boolean=True, description='Not recently verified')
    def stale(self, feature):
        return certification.is_stale(feature)

    @admin.display(description='Guidelines')
    def grading_guidelines(self, feature):
        url = reverse('admin:trails_gradingguidelines_change', args=[1])
        return format_html('{}<p><a href="{}">Edit the guidelines</a></p>',
                           linebreaks(GradingGuidelines.get().body), url)

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    def _run(self, request, queryset, fn, done):
        ok = 0
        for feature in queryset:
            try:
                fn(feature)
                ok += 1
            except certification.CertificationError as exc:
                self.message_user(request, f'{feature.name}: {exc}', messages.ERROR)
        if ok:
            self.message_user(request, f'{done} {ok} feature(s).', messages.SUCCESS)

    @admin.action(description='Submit for review by a second reviewer')
    def submit(self, request, queryset):
        self._run(request, queryset, lambda f: certification.submit(f, request.user), 'Submitted')

    @admin.action(description='Certify (goes live for riders)')
    def certify(self, request, queryset):
        self._run(request, queryset, lambda f: certification.certify(f, request.user), 'Certified')

    @admin.action(description='Flag as changed (needs re-grading)')
    def flag_changed(self, request, queryset):
        self._run(request, queryset, lambda f: certification.flag(f, request.user, Certification.CHANGED), 'Flagged')

    @admin.action(description='Flag as closed (hidden from riders)')
    def flag_closed(self, request, queryset):
        self._run(request, queryset, lambda f: certification.flag(f, request.user, Certification.CLOSED), 'Closed')

    @admin.action(description='Reopen a closed feature as a draft')
    def reopen(self, request, queryset):
        self._run(request, queryset, lambda f: certification.reopen(f, request.user), 'Reopened')

    @admin.action(description='Mark verified (checked, still as graded)')
    def verify(self, request, queryset):
        self._run(request, queryset, lambda f: certification.verify(f, request.user), 'Verified')

    @admin.action(description='Export as feature of the week (zip: cards, photo, post text)')
    def feature_of_the_week(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, 'Pick one feature to export.', messages.WARNING)
            return None
        feature = queryset.select_related('trail__system').get()
        response = HttpResponse(share.feature_of_the_week(feature, request), content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="feature-of-the-week-{feature.pk}.zip"'
        return response

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
    """Riders' "this has changed" reports. Look at the feature, flag it if needed, then resolve or dismiss."""
    list_display = ('feature', 'trail', 'user', 'status', 'note', 'created_at')
    list_filter = ('status',)
    raw_id_fields = ('feature', 'user', 'resolved_by')
    actions = ['resolve', 'dismiss']

    @admin.display(description='Trail')
    def trail(self, report):
        return report.feature.trail

    @admin.action(description='Resolve (dealt with)')
    def resolve(self, request, queryset):
        for r in queryset:
            certification.resolve_report(r, request.user, ReportStatus.RESOLVED)

    @admin.action(description='Dismiss (no change needed)')
    def dismiss(self, request, queryset):
        for r in queryset:
            certification.resolve_report(r, request.user, ReportStatus.DISMISSED)


@admin.register(GradingGuidelines)
class GradingGuidelinesAdmin(admin.ModelAdmin):
    """The one grading document everyone grades from. Markdown."""
    fields = ('body', 'updated_at', 'updated_by')
    readonly_fields = ('updated_at', 'updated_by')

    def changelist_view(self, request, extra_context=None):
        return redirect(reverse('admin:trails_gradingguidelines_change', args=[GradingGuidelines.get().pk]))

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)
