const kind = document.querySelector('#material-kind');
const answer = document.querySelector('#answer-field');
if (kind && answer) {
  const update = () => { answer.hidden = kind.value !== 'question'; };
  kind.addEventListener('change', update);
  update();
}
