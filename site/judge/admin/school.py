from django.contrib import admin
from django import forms

from judge.models import School


class CustomActionForm(forms.Form):
    action = forms.ChoiceField(label="작업", choices=[], required=False)
    select_across = forms.CharField(required=False, widget=forms.HiddenInput(), label='')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['action'].choices.insert(0, ("", "작업을 선택하세요."))


class SchoolAdmin(admin.ModelAdmin):
    list_display = ['name', 'short_name', 'school_type', 'is_jbnu', 'is_active']
    list_filter = ['school_type', 'is_jbnu', 'is_active']
    search_fields = ['name', 'short_name']
    fields = ('name', 'short_name', 'school_type', 'is_jbnu', 'is_active')
    action_form = CustomActionForm
