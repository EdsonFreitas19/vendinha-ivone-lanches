// Habilita o campo "quantidade em estoque" só quando o controle de estoque está marcado.
document.querySelectorAll("[data-track]").forEach(function (box) {
  var form = box.closest("form");
  var stock = form.querySelector("[data-stock]");
  var field = stock.closest("label");
  function update() {
    stock.disabled = !box.checked;
    field.classList.toggle("disabled", !box.checked);
  }
  box.addEventListener("change", update);
  update();
});
