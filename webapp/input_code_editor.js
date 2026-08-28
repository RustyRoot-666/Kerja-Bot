// Make generated workflow output explicit editable CODE before copying.

const _renderWorkflowResultBeforeCodeEditor = renderWorkflowResult;
renderWorkflowResult = function renderWorkflowResultAsEditableCode(action, order, data) {
  const host = workflowHost();
  const outputs = generateWorkflowOutputs(action, data);
  host.innerHTML = `<article class="tool-card">
    <strong>✅ ${action.toUpperCase()} SIAP</strong>
    <small>INET ${esc(order.service_number)} • edit bila perlu, lalu SALIN CODE.</small>
    <div class="info-box" style="margin-top:12px"><span>⌨</span><p><strong style="color:#eef6ff">Output berupa CODE</strong><br>Teknisi menyalin code di bawah lalu menempelkannya ke chat/grup tujuan.</p></div>
    <div id="wfOutputs" style="margin-top:12px"></div>
    <button class="tool-action" id="wfAnother"><b>Kerjakan order lain</b><span>＋</span></button>
    <button class="tool-action" id="wfHome"><b>Kembali ke menu Input</b><span>‹</span></button>
  </article>`;

  const box = document.querySelector('#wfOutputs');
  outputs.forEach(([kind, text], index) => {
    const card = document.createElement('div');
    card.style.marginBottom = '14px';
    card.innerHTML = `<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:7px"><strong>${esc(kind)}</strong><span style="font-size:9px;color:#758ba2">CODE ${index + 1}</span></div>
      <textarea spellcheck="false" style="width:100%;min-height:${kind === 'REPORT' ? '300px' : '250px'};box-sizing:border-box;white-space:pre;overflow:auto;background:#06111f;border:1px solid #203a57;border-radius:12px;padding:12px;font:10px/1.55 monospace;color:#dceaff;resize:vertical">${esc(text)}</textarea>
      <button class="tool-action" type="button"><b>📋 SALIN CODE ${esc(kind)}</b><span>Salin ›</span></button>`;
    const textarea = card.querySelector('textarea');
    card.querySelector('button').addEventListener('click', () => copyText(textarea.value, `Code ${kind} tersalin`));
    box.appendChild(card);
  });

  document.querySelector('#wfAnother')?.addEventListener('click', () => startWorkflow(action));
  document.querySelector('#wfHome')?.addEventListener('click', renderWorkflowHome);
};
