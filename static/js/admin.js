/* timeline-cv 后台交互：wangEditor 初始化 + 提交前同步富文本到隐藏 textarea */
function initEditor(editorId, textareaId) {
  "use strict";
  var E = window.wangEditor;
  if (!E) { console.warn("wangEditor 未加载"); return; }
  var box = document.getElementById(editorId);
  var ta = document.getElementById(textareaId);
  if (!box || !ta) return;
  var editor = new E("#" + editorId);
  editor.config.uploadImgServer = "/adminc/upload";
  editor.config.uploadFileName = "file";
  editor.config.zIndex = 100;
  editor.create();
  editor.txt.html(ta.value);
  var form = ta.closest("form");
  if (form) {
    form.addEventListener("submit", function () {
      ta.value = editor.txt.html();
    });
  }
}


