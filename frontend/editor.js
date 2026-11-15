import { Editor } from '@tiptap/core';
import StarterKit from '@tiptap/starter-kit';
import Image from '@tiptap/extension-image';
import Highlight from '@tiptap/extension-highlight';
import TextAlign from '@tiptap/extension-text-align';
import { TableKit } from '@tiptap/extension-table';
import { TaskList, TaskItem } from '@tiptap/extension-list';

const form = document.querySelector('.editor-form');
let dirty = false;
let submitting = false;
let uploads = 0;
const instances = [];

function legacyDocument(text) {
  return { type: 'doc', content: text.split(/\r?\n/).map(line => ({
    type: 'paragraph', ...(line ? { content: [{ type: 'text', text: line }] } : {}),
  })) };
}

for (const root of document.querySelectorAll('[data-rich-editor]')) {
  const source = root.querySelector('textarea');
  const surface = root.querySelector('.rich-surface');
  const toolbar = root.querySelector('.editor-toolbar');
  const context = root.querySelector('.editor-context');
  const status = root.querySelector('.upload-status');
  const fileInput = root.querySelector('.image-input');
  const linkBox = root.querySelector('.link-popover');
  let editor;

  const synchronize = () => {
    source.value = editor.getHTML();
    const words = editor.getText().trim().split(/\s+/).filter(Boolean).length;
    root.querySelector('.editor-count').textContent = `${words} слов · ${editor.getText().length} символов`;
    for (const button of root.querySelectorAll('[data-command]')) {
      const name = button.dataset.command;
      const active = name.startsWith('align') ? editor.isActive({ textAlign: name.slice(5).toLowerCase() }) : editor.isActive(name);
      button.setAttribute('aria-pressed', String(active));
      if (name === 'undo' || name === 'redo') button.disabled = !editor.can()[name]();
    }
    const heading = [1, 2, 3].find(level => editor.isActive('heading', { level }));
    toolbar.querySelector('.block-style').value = heading ? `heading-${heading}` : 'paragraph';
    const inCode = editor.isActive('codeBlock');
    const inTable = editor.isActive('table');
    context.hidden = !inCode && !inTable;
    root.querySelector('.code-options').hidden = !inCode;
    root.querySelector('.table-options').hidden = !inTable;
    if (inCode) root.querySelector('.code-options select').value = editor.getAttributes('codeBlock').language || 'plaintext';
  };

  async function upload(files) {
    for (const file of files) {
      if (file.size > 5 * 1024 * 1024) {
        status.textContent = 'Изображение должно быть не больше 5 МБ.';
        continue;
      }
      uploads++;
      status.textContent = 'Загружаю изображение…';
      form.querySelector('[type="submit"]').disabled = true;
      try {
        const data = new FormData();
        data.append('image', file);
        data.append('csrf_token', form.elements.csrf_token.value);
        const response = await fetch('/images/upload', { method: 'POST', body: data, credentials: 'same-origin' });
        if (!response.headers.get('content-type')?.includes('application/json')) throw new Error('Не удалось загрузить фото. Обновите страницу и проверьте вход владельца.');
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || 'Загрузка не удалась.');
        editor.chain().focus().setImage({ src: result.url, alt: file.name || 'Изображение' }).run();
        status.textContent = 'Изображение загружено. Сохраните материал, чтобы прикрепить его к записи.';
      } catch (error) {
        status.textContent = error.message || 'Нет соединения. Повторите загрузку.';
      } finally {
        uploads--;
        form.querySelector('[type="submit"]').disabled = uploads > 0;
      }
    }
  }

  editor = new Editor({
    element: surface,
    injectCSS: false,
    extensions: [
      StarterKit.configure({
        heading: { levels: [1, 2, 3] },
        codeBlock: { defaultLanguage: 'plaintext', enableTabIndentation: true, tabSize: 4 },
        link: { openOnClick: false, autolink: true, defaultProtocol: 'https', protocols: ['http', 'https', 'mailto'] },
      }),
      Image.configure({ allowBase64: false, HTMLAttributes: { loading: 'lazy' } }),
      Highlight,
      TextAlign.configure({ types: ['heading', 'paragraph'] }),
      TableKit.configure({ table: { resizable: false } }),
      TaskList, TaskItem.configure({ nested: true }),
    ],
    content: root.dataset.format === 'html' ? source.value : legacyDocument(source.value),
    editorProps: {
      attributes: { class: 'rich-content', role: 'textbox', 'aria-multiline': 'true', 'aria-labelledby': `${root.dataset.field}-label`, 'data-placeholder': 'Начните писать. Здесь можно добавлять код, таблицы, пометки и изображения…' },
      handlePaste(_view, event) {
        const files = [...(event.clipboardData?.files || [])];
        if (!files.length) return false;
        event.preventDefault();
        upload(files);
        return true;
      },
      handleDrop(view, event) {
        const files = [...(event.dataTransfer?.files || [])];
        if (!files.length) return false;
        event.preventDefault();
        const coords = view.posAtCoords({ left: event.clientX, top: event.clientY });
        if (coords) editor.commands.setTextSelection(coords.pos);
        upload(files);
        return true;
      },
    },
    onUpdate() { dirty = true; synchronize(); },
    onSelectionUpdate() { synchronize(); },
  });
  instances.push(editor);
  source.hidden = true;
  surface.hidden = false;
  toolbar.hidden = false;
  root.querySelector('.editor-footer').hidden = false;
  synchronize();

  root.querySelectorAll('[data-command]').forEach(button => {
    button.addEventListener('mousedown', event => event.preventDefault());
    button.addEventListener('click', () => {
      const name = button.dataset.command;
      const toggles = { bold: 'toggleBold', italic: 'toggleItalic', underline: 'toggleUnderline', strike: 'toggleStrike', highlight: 'toggleHighlight', code: 'toggleCode', bulletList: 'toggleBulletList', orderedList: 'toggleOrderedList', taskList: 'toggleTaskList', blockquote: 'toggleBlockquote', codeBlock: 'toggleCodeBlock' };
      const chain = editor.chain().focus();
      if (toggles[name]) chain[toggles[name]]().run();
      else if (name === 'table') chain.insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run();
      else if (name === 'image') fileInput.click();
      else if (name === 'link') {
        linkBox.hidden = !linkBox.hidden;
        const input = linkBox.querySelector('input');
        input.value = editor.getAttributes('link').href || '';
        if (!linkBox.hidden) input.focus();
      } else if (name === 'horizontalRule') chain.setHorizontalRule().run();
      else if (name.startsWith('align')) chain.setTextAlign(name.slice(5).toLowerCase()).run();
      else if (name === 'clear') chain.unsetAllMarks().clearNodes().run();
      else if (typeof chain[name] === 'function') chain[name]().run();
      synchronize();
    });
  });
  toolbar.querySelector('.block-style').addEventListener('change', event => {
    const value = event.target.value;
    if (value === 'paragraph') editor.chain().focus().setParagraph().run();
    else editor.chain().focus().setHeading({ level: Number(value.split('-')[1]) }).run();
    synchronize();
  });
  root.querySelector('.code-options select').addEventListener('change', event => editor.chain().focus().updateAttributes('codeBlock', { language: event.target.value }).run());
  root.querySelector('[data-link-save]').addEventListener('click', () => {
    let href = linkBox.querySelector('input').value.trim();
    if (!href) editor.chain().focus().extendMarkRange('link').unsetLink().run();
    else {
      if (!/^[a-z][\w+.-]*:/i.test(href)) href = `https://${href}`;
      if (!/^(https?:\/\/|mailto:)/i.test(href)) {
        status.textContent = 'Используйте ссылку https://, http:// или mailto:.';
        return;
      }
      editor.chain().focus().extendMarkRange('link').setLink({ href }).run();
    }
    linkBox.hidden = true;
  });
  root.querySelector('[data-link-remove]').addEventListener('click', () => { editor.chain().focus().extendMarkRange('link').unsetLink().run(); linkBox.hidden = true; });
  root.querySelector('[data-link-cancel]').addEventListener('click', () => { linkBox.hidden = true; editor.commands.focus(); });
  fileInput.addEventListener('change', () => { upload([...fileInput.files]); fileInput.value = ''; });
}

if (form && instances.length) {
  form.elements.content_format.value = 'html';
  form.addEventListener('input', () => { dirty = true; });
  form.addEventListener('submit', event => {
    instances.forEach((editor, i) => { document.querySelectorAll('[data-rich-editor] textarea')[i].value = editor.getHTML(); });
    if (uploads > 0) {
      event.preventDefault();
      return;
    }
    const mainEditor = instances[0];
    if (mainEditor.isEmpty) {
      event.preventDefault();
      document.querySelector('.upload-status').textContent = 'Добавьте текст, код или изображение.';
      mainEditor.commands.focus();
      return;
    }
    submitting = true;
  });
  window.addEventListener('beforeunload', event => {
    if (dirty && !submitting) { event.preventDefault(); event.returnValue = ''; }
  });
}
