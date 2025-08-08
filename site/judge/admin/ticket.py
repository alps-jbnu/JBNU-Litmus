from django.contrib import admin
from django.contrib.admin import ModelAdmin
from django.contrib.admin.options import StackedInline
from django.forms import ModelForm
from django.urls import reverse_lazy
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from judge.models import TicketMessage
from judge.widgets import AdminHeavySelect2MultipleWidget, AdminHeavySelect2Widget, AdminMartorWidget


class TicketMessageForm(ModelForm):
    class Meta:
        widgets = {
            'user': AdminHeavySelect2Widget(data_view='profile_select2', attrs={'style': 'width: 100%'}),
            'body': AdminMartorWidget(attrs={'data-markdownfy-url': reverse_lazy('ticket_preview')}),
        }


class TicketMessageInline(StackedInline):
    model = TicketMessage
    form = TicketMessageForm
    fields = ('user', 'body')


class TicketForm(ModelForm):
    class Meta:
        widgets = {
            'user': AdminHeavySelect2Widget(data_view='profile_select2', attrs={'style': 'width: 100%'}),
            'assignees': AdminHeavySelect2MultipleWidget(data_view='profile_select2', attrs={'style': 'width: 100%'}),
        }

class EmptyFilter(admin.SimpleListFilter):
    title = ' ' 
    parameter_name = 'empty'

    def lookups(self, request, model_admin):
        return [('none', '')]  # 더미 값

    def queryset(self, request, queryset):
        return queryset


from django import forms

class CustomActionForm(forms.Form):
    action = forms.ChoiceField(
        label="작업",   
        choices=[],           
        required=False,
    )
    select_across = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),   
        label=''
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['action'].choices.insert(0, ("", "작업을 선택하세요."))

class TicketAdmin(ModelAdmin):
    fields = ('title', 'time', 'user', 'assignees', 'content_type', 'object_id', 'notes')
    readonly_fields = ('time',)
    list_display = ('title', 'user', 'time_display', 'linked_item')
    inlines = [TicketMessageInline]
    form = TicketForm
    date_hierarchy = 'time'
    list_filter = [EmptyFilter]  # 필터 박스만 강제로 출력
    
    action_form = CustomActionForm

    

    def time_display(self, obj):
        """작성일을 한국 형식으로 표시"""
        if obj.time:
            return obj.time.strftime('%Y. %m. %d. %H:%M')
        return '-'
    
    time_display.admin_order_field = 'time'
    time_display.short_description = _('작성일')
