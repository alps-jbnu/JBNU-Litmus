(function () {
    // 사이트 테마(<html data-theme="dark">)에 맞춰 에디터 테마를 고른다.
    // 서버에서 고르지 않는 이유: 프로필의 '시스템 기본값(auto)' 은 브라우저의
    // prefers-color-scheme 으로만 판정되므로 서버가 알 수 없다. 여기서 판정하면
    // light / dark / auto 세 경우가 모두 자동으로 맞는다.
    var editors = [];

    function siteIsDark() {
        return document.documentElement.getAttribute('data-theme') === 'dark';
    }

    function resolveTheme(widget) {
        var dark = widget.getAttribute('data-theme-dark');
        if (dark && siteIsDark()) {
            return dark;
        }
        return widget.getAttribute('data-theme');
    }

    function applyTheme(entry) {
        var theme = resolveTheme(entry.widget);
        if (theme) {
            entry.editor.setTheme('ace/theme/' + theme);
        }
    }

    // '시스템 기본값' 사용자가 OS 테마를 바꾸면 base.html 이 새로고침 없이
    // <html data-theme> 만 토글한다. 그때 에디터도 같이 따라가도록 감시한다.
    function watchSiteTheme() {
        if (!window.MutationObserver) {
            return;
        }
        new MutationObserver(function () {
            for (var i = 0; i < editors.length; i++) {
                applyTheme(editors[i]);
            }
        }).observe(document.documentElement, {attributes: true, attributeFilter: ['data-theme']});
    }

    function getDocHeight() {
        var D = document;
        return Math.max(
            Math.max(D.body.scrollHeight, D.documentElement.scrollHeight),
            Math.max(D.body.offsetHeight, D.documentElement.offsetHeight),
            Math.max(D.body.clientHeight, D.documentElement.clientHeight)
        );
    }

    function getDocWidth() {
        var D = document;
        return Math.max(
            Math.max(D.body.scrollWidth, D.documentElement.scrollWidth),
            Math.max(D.body.offsetWidth, D.documentElement.offsetWidth),
            Math.max(D.body.clientWidth, D.documentElement.clientWidth)
        );
    }

    function next(elem) {
        // Credit to John Resig for this function
        // taken from Pro JavaScript techniques
        do {
            elem = elem.nextSibling;
        } while (elem && elem.nodeType != 1);
        return elem;
    }

    function prev(elem) {
        // Credit to John Resig for this function
        // taken from Pro JavaScript techniques
        do {
            elem = elem.previousSibling;
        } while (elem && elem.nodeType != 1);
        return elem;
    }

    function redraw(element) {
        element = $(element);
        var n = document.createTextNode(' ');
        element.appendChild(n);
        (function () {
            n.parentNode.removeChild(n)
        }).defer();
        return element;
    }

    function minimizeMaximize(widget, main_block, editor) {
        if (window.fullscreen == true) {
            main_block.className = 'django-ace-editor';

            widget.style.width = window.ace_widget.width + 'px';
            widget.style.height = window.ace_widget.height + 'px';
            window.fullscreen = false;
        }
        else {
            window.ace_widget = {
                'width': widget.offsetWidth,
                'height': widget.offsetHeight
            };

            main_block.className = 'django-ace-editor-fullscreen';

            widget.style.height = getDocHeight() + 'px';
            widget.style.width = getDocWidth() + 'px';

            window.scrollTo(0, 0);
            window.fullscreen = true;
        }
        editor.resize();
    }

    function apply_widget(widget) {
        var div = widget.firstChild,
            textarea = next(widget),
            editor = ace.edit(div),
            mode = widget.getAttribute('data-mode'),
            wordwrap = widget.getAttribute('data-wordwrap'),
            toolbar = prev(widget),
            main_block = toolbar.parentNode;

        // Toolbar maximize/minimize button
        var min_max = toolbar.getElementsByClassName('django-ace-max_min');
        min_max[0].onclick = function () {
            minimizeMaximize(widget, main_block, editor);
            return false;
        };

        editor.getSession().setValue(textarea.value);

        // the editor is initially absolute positioned
        textarea.style.display = "none";

        // options
        if (mode) {
            editor.getSession().setMode('ace/mode/' + mode);
        }
        var entry = {widget: widget, editor: editor};
        editors.push(entry);
        applyTheme(entry);

        if (wordwrap == "true") {
            editor.getSession().setUseWrapMode(true);
        }

        editor.getSession().on('change', function () {
            textarea.value = editor.getSession().getValue();
        });

        editor.commands.addCommands([
            {
                name: 'Full screen',
                bindKey: {win: 'Ctrl-F11', mac: 'Command-F11'},
                exec: function (editor) {
                    minimizeMaximize(widget, main_block, editor);
                },
                readOnly: true // false if this command should not apply in readOnly mode
            },
            {
                name: 'submit',
                bindKey: {win: 'Ctrl+Enter', mac: 'Command+Enter'},
                exec: function (editor) {
                    $('form#problem_submit').submit();
                },
                readOnly: true
            },
            {
                name: "showKeyboardShortcuts",
                bindKey: {win: "Ctrl-Shift-/", mac: "Command-Shift-/"},
                exec: function (editor) {
                    ace.config.loadModule("ace/ext/keybinding_menu", function (module) {
                        module.init(editor);
                        editor.showKeyboardShortcuts();
                    });
                }
            },
            {
                name: "increaseFontSize",
                bindKey: "Ctrl-+",
                exec: function (editor) {
                    var size = parseInt(editor.getFontSize(), 10) || 12;
                    editor.setFontSize(size + 1);
                }
            },
            {
                name: "decreaseFontSize",
                bindKey: "Ctrl+-",
                exec: function (editor) {
                    var size = parseInt(editor.getFontSize(), 10) || 12;
                    editor.setFontSize(Math.max(size - 1 || 1));
                }
            },
            {
                name: "resetFontSize",
                bindKey: "Ctrl+0",
                exec: function (editor) {
                    editor.setFontSize(12);
                }
            }
        ]);

        window[widget.id] = editor;
        $(widget).trigger('ace_load', [editor]);
    }

    function init() {
        var widgets = document.getElementsByClassName('django-ace-widget');

        for (var i = 0; i < widgets.length; i++) {
            var widget = widgets[i];
            widget.className = "django-ace-widget"; // remove `loading` class

            apply_widget(widget);
        }

        watchSiteTheme();
    }

    if (window.addEventListener) { // W3C
        window.addEventListener('load', init);
    } else if (window.attachEvent) { // Microsoft
        window.attachEvent('onload', init);
    }
})();
