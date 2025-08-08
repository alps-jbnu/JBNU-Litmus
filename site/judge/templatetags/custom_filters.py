# myapp/templatetags/custom_filters.py
from django import template
from django.utils.safestring import mark_safe

register = template.Library()

@register.filter
def insert_ul(form_html):
    # <tr> 태그로 폼 HTML 분리
    rows = form_html.split('</tr>')
    ul_html = '<ul><li>여기에 UL 내용 추가</li></ul>'  # 필요한 내용으로 수정
    new_html = ''

    # 각 행을 반복하면서 <ul>을 행 사이에 추가
    for i in range(len(rows) - 1):
        new_html += rows[i] + '</tr>' + ul_html

    new_html += rows[-1]  # 마지막 부분 추가 (추가 <ul> 없음)

    return mark_safe(new_html)
