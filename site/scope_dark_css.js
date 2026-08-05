#!/usr/bin/env node
/*
 * 다크 테마 스타일시트를 [data-theme="dark"] 아래로 스코프한다.
 *
 * 원래 다크모드는 서버가 style.css / dark/style.css 중 하나를 골라 내보내는 방식이었다.
 * 그래서 서버가 알 수 없는 '시스템 기본값'(auto)에서는 항상 밝은 style.css가 나가고,
 * 클라이언트가 붙이는 <html data-theme="dark">만 적용돼 색이 뒤섞였다.
 *
 * 여기서 다크 빌드 결과 전체를 :where([data-theme="dark"]) 로 감싸두면
 * 두 스타일시트를 항상 같이 로드할 수 있고, 테마 판정은 오직 data-theme 속성 하나로 끝난다.
 *
 * :where() 를 쓰는 이유는 특이도(specificity)를 0으로 유지하기 위해서다.
 * 다크 규칙이 밝은 규칙보다 특이도가 높아지면, base.html 인라인 <style> 의
 * var(--...) 기반 규칙들을 밀어내면서 기존 Dark 모드 화면이 바뀌어 버린다.
 * 특이도를 그대로 두면 로드 순서(밝은 것 → 어두운 것)만으로 승패가 갈린다.
 */
const fs = require('fs');
const postcss = require('postcss');

const SCOPE = ':where([data-theme="dark"])';

// 자식이 규칙(rule)인 at-rule 중, 스코프를 내려보내야 하는 것들.
// @keyframes 의 자식은 'from/to/50%' 이므로 절대 건드리면 안 된다.
const TRANSPARENT_ATRULES = new Set(['media', 'supports', 'layer', 'container']);

function scopeSelector(selector) {
    const sel = selector.trim();
    if (!sel) return sel;
    // 이미 스코프된 경우 (재실행 안전성)
    if (sel.startsWith(SCOPE)) return sel;
    // html 자신에게 붙는 규칙은 자손 결합자로 감쌀 수 없다 -> 같은 요소에 붙인다.
    if (sel === 'html' || sel.startsWith('html:') || sel.startsWith('html.') ||
        sel.startsWith('html[') || sel.startsWith('html ') || sel.startsWith('html>')) {
        return sel.replace(/^html/, `html${SCOPE}`);
    }
    if (sel === ':root') return `:root${SCOPE}`;
    return `${SCOPE} ${sel}`;
}

function isScopable(rule) {
    let parent = rule.parent;
    while (parent) {
        if (parent.type === 'root') return true;
        if (parent.type === 'atrule') {
            if (!TRANSPARENT_ATRULES.has(parent.name.toLowerCase())) return false;
        } else if (parent.type === 'rule') {
            // 중첩 규칙은 부모가 이미 스코프되므로 건드리지 않는다.
            return false;
        }
        parent = parent.parent;
    }
    return true;
}

const scopeDark = () => ({
    postcssPlugin: 'scope-dark',
    Once(root) {
        root.walkRules((rule) => {
            if (!isScopable(rule)) return;
            rule.selectors = rule.selectors.map(scopeSelector);
        });
    },
});
scopeDark.postcss = true;

const files = process.argv.slice(2);
if (!files.length) {
    console.error('usage: scope_dark_css.js <css-file>...');
    process.exit(1);
}

(async () => {
    for (const file of files) {
        const css = fs.readFileSync(file, 'utf8');
        const result = await postcss([scopeDark()]).process(css, { from: file, to: file });
        fs.writeFileSync(file, result.css);
        console.log(`Scoped ${file} under ${SCOPE}`);
    }
})().catch((err) => {
    console.error(err);
    process.exit(1);
});
