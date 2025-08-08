from django.forms import ModelForm
from django.urls import reverse_lazy
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _, ngettext
from reversion.admin import VersionAdmin

from judge.models import Comment
from judge.widgets import AdminHeavySelect2Widget, AdminMartorWidget
from django.contrib import admin
from django.contrib.admin.filters import FieldListFilter
from operator import itemgetter

class CommentForm(ModelForm):
    class Meta:
        widgets = {
            'author': AdminHeavySelect2Widget(data_view='profile_select2'),
            'parent': AdminHeavySelect2Widget(data_view='comment_select2'),
            'body': AdminMartorWidget(attrs={'data-markdownfy-url': reverse_lazy('comment_preview')}),
        }
        
class CombinedCommnetFilter(FieldListFilter):
    title = ' '
    template = 'admin/input_filter/input_filter_comment.html'  # 템플릿 따로 필요
    
    def __init__(self, field, request, params, model, model_admin, field_path):
        super().__init__(field, request, params, model, model_admin, field_path)
        self.request = request
        self.params = params
        
     



    def expected_parameters(self):
        return ['is_public']

    def choices(self, changelist):
        yield {
            'selected': False,
            'query_string': changelist.get_query_string(remove=self.expected_parameters()),
            'display': '초기화',
        }

    def queryset(self, request, queryset):
        is_public = request.GET.get('is_public')
        
        if is_public in ['True', 'False']:
            queryset = queryset.filter(is_public=(is_public == 'True'))
            
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

class CommentAdmin(VersionAdmin):
    fieldsets = (
        (None, {'fields': ('author', 'page', 'parent', 'time', 'score', 'hidden')}),
        (_('Content'), {'fields': ('body',)}),
    )
    list_display = ['author', 'linked_page', 'time_display', 'score', 'hidden_status']
    search_fields = ['author__user__username', 'page', 'body']
    actions = ['hide_comment', 'unhide_comment']
    list_filter = (
        ('id', CombinedCommnetFilter),
    )
    readonly_fields = ['time', 'score']
    actions_on_top = True
    actions_on_bottom = True
    form = CommentForm
    date_hierarchy = 'time'
    action_form = CustomActionForm
    

    

    def hidden_status(self, obj):
        """관리자 페이지에서 댓글 숨김 상태를 pill 스타일로 표시"""
        if obj.hidden:
            return format_html('<span class="pill pill-warning">비공개</span>')
        else:
            return format_html('<span class="pill pill-success">공개</span>')
    
    hidden_status.admin_order_field = 'hidden'
    hidden_status.short_description = _('공개')

    def time_display(self, obj):
        """댓글 시간을 한국 형식으로 표시"""
        if obj.time:
            return obj.time.strftime('%Y. %m. %d. %H:%M')
        return '-'
    
    time_display.admin_order_field = 'time'
    time_display.short_description = _('게시 시각')

    def get_queryset(self, request):
        return Comment.objects.order_by('-time')

    def hide_comment(self, request, queryset):
        count = queryset.update(hidden=True)
        self.message_user(request, ngettext('%d comment successfully hidden.',
                                            '%d comments successfully hidden.',
                                            count) % count)
    hide_comment.short_description = _('Hide comments')

    def unhide_comment(self, request, queryset):
        count = queryset.update(hidden=False)
        self.message_user(request, ngettext('%d comment successfully unhidden.',
                                            '%d comments successfully unhidden.',
                                            count) % count)
    unhide_comment.short_description = _('Unhide comments')

    def linked_page(self, obj):
        link = obj.link
        if link is not None:
            return format_html('<a href="{0}">{1}</a>', link, obj.page)
        else:
            return format_html('{0}', obj.page)
    linked_page.short_description = _('Associated page')
    linked_page.admin_order_field = 'page'

    def save_model(self, request, obj, form, change):
        super(CommentAdmin, self).save_model(request, obj, form, change)
        if obj.hidden:
            obj.get_descendants().update(hidden=obj.hidden)
