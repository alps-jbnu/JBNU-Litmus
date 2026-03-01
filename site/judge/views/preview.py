from django.http import HttpResponseBadRequest
from django.views.generic.base import ContextMixin, TemplateResponseMixin, View

from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
import re


def latex_to_markdown(text):
    """LaTeX 구조 명령어를 Markdown 문법으로 변환 (Markdown 필터 실행 전에 처리)"""
    # verbatim 블록을 먼저 보호
    verbatim_blocks = []
    def save_verbatim(m):
        verbatim_blocks.append(m.group(1))
        return '__VERBATIM_%d__' % (len(verbatim_blocks) - 1)
    text = re.sub(r'\\begin\{verbatim\}([\s\S]*?)\\end\{verbatim\}', save_verbatim, text)

    # 독립 줄의 $...\n...\n$ 형식 display math → $$ ... $$ 로 변환
    # (Mistune block_math 규칙이 $$...$$를 \[...\]로 변환, MathJax가 렌더링)
    text = re.sub(r'(?m)^\$\n([\s\S]+?)\n\$$', lambda m: '$$\n%s\n$$' % m.group(1), text)

    # \section*{제목} → ## 제목
    text = re.sub(r'\\section\*\{([^}]+)\}', r'## \1', text)
    # \subsection*{제목} → ### 제목
    text = re.sub(r'\\subsection\*\{([^}]+)\}', r'### \1', text)
    # \subsubsection*{제목} → #### 제목
    text = re.sub(r'\\subsubsection\*\{([^}]+)\}', r'#### \1', text)
    # \textbf{텍스트} → **텍스트**
    text = re.sub(r'\\textbf\{([^}]+)\}', r'**\1**', text)
    # \textit{텍스트} → *텍스트*
    text = re.sub(r'\\textit\{([^}]+)\}', r'*\1*', text)
    # \InputFile / \OutputFile
    text = text.replace('\\InputFile', '## 입력')
    text = text.replace('\\OutputFile', '## 출력')

    # \begin{itemize}...\end{itemize}
    def convert_itemize(m):
        items = re.split(r'\\item\s*', m.group(1))
        return '\n'.join('- ' + i.strip() for i in items if i.strip())
    text = re.sub(r'\\begin\{itemize\}([\s\S]*?)\\end\{itemize\}', convert_itemize, text)

    # \begin{enumerate}...\end{enumerate}
    def convert_enumerate(m):
        items = re.split(r'\\item\s*', m.group(1))
        return '\n'.join('%d. %s' % (i + 1, item.strip())
                         for i, item in enumerate(item for item in items if item.strip()))
    text = re.sub(r'\\begin\{enumerate\}([\s\S]*?)\\end\{enumerate\}', convert_enumerate, text)

    # verbatim 블록 복원 → 코드 블록
    for i, content in enumerate(verbatim_blocks):
        text = text.replace('__VERBATIM_%d__' % i, '\n```\n%s\n```\n' % content.strip())

    return text


@method_decorator(csrf_exempt, name='dispatch')
class MarkdownPreviewView(TemplateResponseMixin, ContextMixin, View):
    def post(self, request, *args, **kwargs):
        try:
            self.preview_data = data = request.POST['content']
        except KeyError:
            return HttpResponseBadRequest('No preview data specified.')

        return self.render_to_response(self.get_context_data(
            preview_data=data,
        ))


class ProblemMarkdownPreviewView(MarkdownPreviewView):
    template_name = 'problem/preview.html'

    def post(self, request, *args, **kwargs):
        try:
            data = request.POST['content']
            data = latex_to_markdown(data)
            self.preview_data = data
        except KeyError:
            return HttpResponseBadRequest('No preview data specified.')

        return self.render_to_response(self.get_context_data(
            preview_data=data,
        ))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['MATH_ENGINE'] = 'jax'
        context['REQUIRE_JAX'] = True
        return context


class BlogMarkdownPreviewView(MarkdownPreviewView):
    template_name = 'blog/preview.html'


class ContestMarkdownPreviewView(MarkdownPreviewView):
    template_name = 'contest/preview.html'


class CommentMarkdownPreviewView(MarkdownPreviewView):
    template_name = 'comments/preview.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['MATH_ENGINE'] = 'jax'
        context['REQUIRE_JAX'] = True
        return context


class FlatPageMarkdownPreviewView(MarkdownPreviewView):
    template_name = 'flatpage-preview.html'


class ProfileMarkdownPreviewView(MarkdownPreviewView):
    template_name = 'user/preview.html'


# class OrganizationMarkdownPreviewView(MarkdownPreviewView):
#     template_name = 'organization/preview.html'


class SolutionMarkdownPreviewView(MarkdownPreviewView):
    template_name = 'solution-preview.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['MATH_ENGINE'] = 'jax'
        context['REQUIRE_JAX'] = True
        return context


class LicenseMarkdownPreviewView(MarkdownPreviewView):
    template_name = 'license-preview.html'


class TicketMarkdownPreviewView(MarkdownPreviewView):
    template_name = 'ticket/preview.html'


class DefaultMarkdownPreviewView(MarkdownPreviewView):
    template_name = 'default-preview.html'
