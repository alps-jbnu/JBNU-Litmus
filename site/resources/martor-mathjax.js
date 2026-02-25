;(function (root, factory) {
    var jq = (root.django && root.django.jQuery) ? root.django.jQuery : root.jQuery;
    if (!jq) {
        return;
    }
    factory(jq);
})(window, function ($) {
    $(document).on('martor:preview', function (e, $content) {
        // LaTeX 문서 구조를 HTML로 변환하는 함수
        function convertLatexToHtml(html) {
            // 먼저 verbatim 환경을 보호 (MathJax가 건드리지 않도록)
            var verbatimBlocks = [];
            html = html.replace(/\\begin\{verbatim\}([\s\S]*?)\\end\{verbatim\}/g, function(match, content) {
                var index = verbatimBlocks.length;
                verbatimBlocks.push(content);
                return '___VERBATIM_BLOCK_' + index + '___';
            });

            // code/pre 블록 보호 (LaTeX 변환 대상에서 제외)
            var htmlBlocks = [];
            html = html.replace(/<pre[\s\S]*?<\/pre>/gi, function(match) {
                var index = htmlBlocks.length;
                htmlBlocks.push(match);
                return '___HTML_BLOCK_' + index + '___';
            });
            html = html.replace(/<code[\s\S]*?<\/code>/gi, function(match) {
                var index = htmlBlocks.length;
                htmlBlocks.push(match);
                return '___HTML_BLOCK_' + index + '___';
            });

            // \section*{제목} → <h3>제목</h3>
            html = html.replace(/\\section\*\{([^}]+)\}/g, '<h3>$1</h3>');

            // \subsection*{부제목} → <h4>부제목</h4>
            html = html.replace(/\\subsection\*\{([^}]+)\}/g, '<h4>$1</h4>');

            // \subsubsection*{소제목} → <h5>소제목</h5>
            html = html.replace(/\\subsubsection\*\{([^}]+)\}/g, '<h5>$1</h5>');

            // \textbf{텍스트} → <strong>텍스트</strong>
            html = html.replace(/\\textbf\{([^}]+)\}/g, '<strong>$1</strong>');

            // \textit{텍스트} → <em>텍스트</em>
            html = html.replace(/\\textit\{([^}]+)\}/g, '<em>$1</em>');

            // \begin{itemize}...\end{itemize} → <ul>...</ul>
            html = html.replace(/\\begin\{itemize\}([\s\S]*?)\\end\{itemize\}/g, function(match, content) {
                // \item을 <li>로 변환
                var items = content.split(/\\item\s+/).map(function (item) {
                    return item.trim();
                }).filter(Boolean).map(function (item) {
                    return '<li>' + item + '</li>';
                }).join('');
                return '<ul>' + items + '</ul>';
            });

            // \begin{enumerate}...\end{enumerate} → <ol>...</ol>
            html = html.replace(/\\begin\{enumerate\}([\s\S]*?)\\end\{enumerate\}/g, function(match, content) {
                // \item을 <li>로 변환
                var items = content.split(/\\item\s+/).map(function (item) {
                    return item.trim();
                }).filter(Boolean).map(function (item) {
                    return '<li>' + item + '</li>';
                }).join('');
                return '<ol>' + items + '</ol>';
            });

            // verbatim 블록 복원
            html = html.replace(/___VERBATIM_BLOCK_(\d+)___/g, function(match, index) {
                var content = verbatimBlocks[parseInt(index, 10)];
                // HTML 엔티티 이스케이프
                var escaped = content
                    .replace(/&/g, '&amp;')
                    .replace(/</g, '&lt;')
                    .replace(/>/g, '&gt;')
                    .replace(/"/g, '&quot;')
                    .replace(/'/g, '&#039;');
                return '<pre><code>' + escaped + '</code></pre>';
            });

            // 보호했던 HTML 블록 복원
            html = html.replace(/___HTML_BLOCK_(\d+)___/g, function(match, index) {
                return htmlBlocks[parseInt(index, 10)];
            });

            return html;
        }

        function update_math() {
            MathJax.typesetPromise([$content[0]]).then(function () {
                $content.find('.tex-image').hide();
                $content.find('.tex-text').show();
            });
        }

        // LaTeX 변환을 먼저 적용
        var currentHtml = $content.html();
        var convertedHtml = convertLatexToHtml(currentHtml);
        if (currentHtml !== convertedHtml) {
            $content.html(convertedHtml);
        }

        var $jax = $content.hasClass('require-mathjax-support') ? $content : $content.find('.require-mathjax-support');
        if ($jax.length) {
            if (!('MathJax' in window)) {
                $.ajax({
                    type: 'GET',
                    url: $jax.attr('data-config'),
                    dataType: 'script',
                    cache: true,
                    success: function () {
                        window.MathJax.startup = {typeset: false};
                        $.ajax({
                            type: 'GET',
                            url: 'https://cdnjs.cloudflare.com/ajax/libs/mathjax/3.2.0/es5/tex-chtml.min.js',
                            dataType: 'script',
                            cache: true,
                            success: update_math
                        });
                    }
                });
            } else {
                update_math();
            }
        }
    })

});
