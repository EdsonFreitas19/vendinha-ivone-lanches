(function () {
  "use strict";

  var brl = function (cents) {
    return "R$ " + (cents / 100).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  };
  var $ = function (id) { return document.getElementById(id); };

  var cfg = $("cart-config");
  var WA = (cfg.dataset.whatsapp || "").replace(/\D/g, "");
  var STORE = cfg.dataset.store || "";
  var KEY = "ivone-cart-v1";

  // ---- catálogo lido da própria página ----
  var catalog = {};
  document.querySelectorAll("#menu .card").forEach(function (el) {
    var d = el.dataset;
    catalog[d.id] = {
      id: d.id, name: d.name, desc: d.desc, price: parseInt(d.price, 10), cat: d.cat,
      img: d.img, status: d.status, max: parseInt(d.max, 10), stock: d.stock,
    };
  });

  // ---- carrinho: { id: quantidade } ----
  var cart = {};
  try { cart = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) { cart = {}; }

  function reconcile() {
    // remove itens que sumiram/ficaram indisponíveis e ajusta ao estoque atual
    Object.keys(cart).forEach(function (id) {
      var it = catalog[id];
      if (!it || it.status !== "ok" || !(cart[id] > 0)) { delete cart[id]; return; }
      cart[id] = Math.min(cart[id], it.max);
    });
  }
  function save() {
    try { localStorage.setItem(KEY, JSON.stringify(cart)); } catch (e) { /* sem armazenamento: segue sem salvar */ }
  }
  function totals() {
    var count = 0, sum = 0;
    Object.keys(cart).forEach(function (id) { count += cart[id]; sum += cart[id] * catalog[id].price; });
    return { count: count, sum: sum };
  }
  function refreshBar() {
    var t = totals();
    $("cartbar").hidden = t.count === 0;
    $("cart-count").textContent = t.count + (t.count === 1 ? " item" : " itens");
    $("cart-total").textContent = brl(t.sum);
  }

  reconcile(); save(); refreshBar();

  // ---- modal de detalhe ----
  var dlg = $("item-dialog");
  var current = null, qty = 1;

  function setQty(n) {
    var max = current.max;
    qty = Math.max(1, Math.min(n, max));
    $("d-qty").textContent = qty;
    $("d-minus").disabled = qty <= 1;
    $("d-plus").disabled = qty >= max;
  }

  function openItem(id) {
    var it = catalog[id];
    if (!it) return;
    current = it;
    $("d-cat").textContent = it.cat;
    $("d-name").textContent = it.name;
    $("d-desc").textContent = it.desc;
    $("d-desc").hidden = !it.desc;
    $("d-price").textContent = brl(it.price);
    if (it.img) { $("d-img").src = it.img; $("d-img").alt = it.name; $("d-img").hidden = false; $("d-noimg").hidden = true; }
    else { $("d-img").hidden = true; $("d-img").removeAttribute("src"); $("d-img").alt = ""; $("d-noimg").hidden = false; }

    var note = $("d-status");
    var row = $("d-qty-row");
    note.className = "status-note";
    if (it.status === "unavailable") { note.textContent = "Este item está indisponível no momento."; note.classList.add("unavailable"); row.hidden = true; }
    else if (it.status === "soldout") { note.textContent = "Esgotado por enquanto."; note.classList.add("soldout"); row.hidden = true; }
    else {
      row.hidden = false;
      note.textContent = it.stock !== "" ? "Em estoque: " + it.stock : "";
    }
    if (it.status === "ok") {
      var inCart = cart[id] || 0;
      var room = it.max - inCart;
      if (room <= 0) {
        note.textContent = "Você já adicionou a quantidade máxima disponível.";
        row.hidden = true;
      } else {
        current = Object.assign({}, it, { max: room });
        setQty(1);
      }
    }
    dlg.showModal();
  }

  document.querySelectorAll("#menu .card").forEach(function (el) {
    el.addEventListener("click", function () { openItem(el.dataset.id); });
  });
  $("d-minus").addEventListener("click", function () { setQty(qty - 1); });
  $("d-plus").addEventListener("click", function () { setQty(qty + 1); });
  $("d-add").addEventListener("click", function () {
    var id = current.id;
    cart[id] = Math.min((cart[id] || 0) + qty, catalog[id].max);
    save(); refreshBar(); dlg.close();
  });

  // ---- modal do pedido ----
  var cdlg = $("cart-dialog");

  function renderCart() {
    var list = $("cart-list");
    list.textContent = "";
    var ids = Object.keys(cart);
    ids.forEach(function (id) {
      var it = catalog[id];
      var li = document.createElement("li");

      var name = document.createElement("div");
      name.className = "ci-name";
      var strong = document.createElement("strong"); strong.textContent = it.name;
      var small = document.createElement("small"); small.textContent = brl(it.price) + " cada";
      name.appendChild(strong); name.appendChild(small);

      var st = document.createElement("div");
      st.className = "stepper small";
      var minus = document.createElement("button"); minus.type = "button"; minus.textContent = "−";
      var out = document.createElement("output"); out.textContent = cart[id];
      var plus = document.createElement("button"); plus.type = "button"; plus.textContent = "+";
      plus.disabled = cart[id] >= it.max;
      minus.addEventListener("click", function () { cart[id] -= 1; if (cart[id] <= 0) delete cart[id]; save(); refreshBar(); renderCart(); });
      plus.addEventListener("click", function () { if (cart[id] < it.max) { cart[id] += 1; save(); refreshBar(); renderCart(); } });
      st.appendChild(minus); st.appendChild(out); st.appendChild(plus);

      var sub = document.createElement("div");
      sub.className = "ci-sub"; sub.textContent = brl(cart[id] * it.price);

      li.appendChild(name); li.appendChild(st); li.appendChild(sub);
      list.appendChild(li);
    });
    var empty = ids.length === 0;
    $("c-total").textContent = brl(totals().sum);
    $("c-send").disabled = empty || !WA;
    $("c-clear").hidden = empty;
    $("c-hint").textContent = empty
      ? "Seu pedido está vazio."
      : (WA ? "Você será levado ao WhatsApp com o pedido pronto. O pagamento é combinado por lá."
            : "Pedidos online ainda não estão configurados nesta loja.");
    if (empty) cdlg.close();
  }

  $("open-cart").addEventListener("click", function () { renderCart(); if (Object.keys(cart).length) cdlg.showModal(); });
  $("c-clear").addEventListener("click", function () { cart = {}; save(); refreshBar(); renderCart(); });
  $("c-send").addEventListener("click", function () {
    var lines = ["Olá! Gostaria de fazer um pedido na " + STORE + ":", ""];
    Object.keys(cart).forEach(function (id) {
      var it = catalog[id];
      lines.push("• " + cart[id] + "x " + it.name + " — " + brl(cart[id] * it.price));
    });
    lines.push("", "Total: " + brl(totals().sum));
    window.open("https://wa.me/" + WA + "?text=" + encodeURIComponent(lines.join("\n")), "_blank", "noopener");
  });

  // ---- fechar modais (botão ×, clique fora, Esc já é nativo) ----
  document.querySelectorAll("dialog [data-close]").forEach(function (b) {
    b.addEventListener("click", function () { b.closest("dialog").close(); });
  });
  document.querySelectorAll("dialog.modal").forEach(function (d) {
    d.addEventListener("click", function (e) { if (e.target === d) d.close(); });
  });
})();
