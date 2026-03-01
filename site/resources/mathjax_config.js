window.MathJax = {
    loader: {
        load: ['[tex]/noerrors']
    },
    tex: {
        inlineMath: [
            ['$', '$'],
            ['~', '~'],
            ['\\(', '\\)']
        ],
        displayMath: [
            ['$$', '$$'],
            ['\\[', '\\]']
        ],
        packages: {'[+]': ['noerrors']},
        processEscapes: true
    },
    options: {
        enableMenu: false
    }
};
