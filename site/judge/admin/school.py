from django.contrib import admin
from django import forms
from django.contrib.admin.filters import FieldListFilter
from django.db.models import Case, When, Value, IntegerField

from judge.models import School


class CombinedSchoolFilter(FieldListFilter):
    title = ' '
    template = 'admin/input_filter/input_filter_school.html'

    def __init__(self, field, request, params, model, model_admin, field_path):
        super().__init__(field, request, params, model, model_admin, field_path)
        self.request = request
        self.params = params

        self.__school_type_lookups = tuple(School.SCHOOL_TYPES)
        self.__school_type_handles = set(value for value, _ in self.__school_type_lookups)

        self.__is_jbnu_lookups = (('1', '전북대'), ('0', '전북대 아님'))
        self.__is_active_lookups = (('1', '활성'), ('0', '비활성'))
        self.__boolean_handles = {'1', '0'}

        self.filter_keys = ['school_type', 'is_jbnu', 'is_active']

    @property
    def school_type_lookups(self):
        return self.__school_type_lookups

    @property
    def is_jbnu_lookups(self):
        return self.__is_jbnu_lookups

    @property
    def is_active_lookups(self):
        return self.__is_active_lookups

    def expected_parameters(self):
        return ['school_type', 'is_jbnu', 'is_active']

    def choices(self, changelist):
        yield {
            'selected': False,
            'query_string': changelist.get_query_string(remove=self.expected_parameters()),
            'display': '초기화',
        }

    def queryset(self, request, queryset):
        school_type = request.GET.get('school_type')
        is_jbnu = request.GET.get('is_jbnu')
        is_active = request.GET.get('is_active')

        if school_type in self.__school_type_handles:
            queryset = queryset.filter(school_type=school_type)

        if is_jbnu in self.__boolean_handles:
            queryset = queryset.filter(is_jbnu=(is_jbnu == '1'))

        if is_active in self.__boolean_handles:
            queryset = queryset.filter(is_active=(is_active == '1'))

        return queryset


class CustomActionForm(forms.Form):
    action = forms.ChoiceField(label="작업", choices=[], required=False)
    select_across = forms.CharField(required=False, widget=forms.HiddenInput(), label='')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['action'].choices.insert(0, ("", "작업을 선택하세요."))


class SchoolAdmin(admin.ModelAdmin):
    list_display = ['name', 'short_name', 'school_type', 'is_jbnu', 'is_active']
    list_filter = (
        ('id', CombinedSchoolFilter),
    )
    search_fields = ['name', 'short_name']
    fields = ('name', 'short_name', 'school_type', 'is_jbnu', 'is_active')
    action_form = CustomActionForm

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(
            type_order=Case(
                When(school_type='highschool', then=Value(0)),
                When(school_type='middleschool', then=Value(1)),
                default=Value(2),
                output_field=IntegerField(),
            ),
        ).order_by('-is_jbnu', 'type_order', 'name')
