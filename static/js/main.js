(() => {
  "use strict";

  const qs = (selector, scope = document) => scope.querySelector(selector);
  const qsa = (selector, scope = document) => [...scope.querySelectorAll(selector)];

  function setDrawer(drawer, overlay, open) {
    if (!drawer) return;
    drawer.classList.toggle("open", open);
    drawer.setAttribute("aria-hidden", String(!open));
    if (overlay) overlay.hidden = !open;
    document.body.classList.toggle("drawer-open", open);
    qs("[data-menu-open]")?.setAttribute("aria-expanded", String(open));
    if (open) qs("button, a", drawer)?.focus();
  }

  const drawer = qs("[data-mobile-drawer]");
  const overlay = qs("[data-drawer-overlay]");
  qs("[data-menu-open]")?.addEventListener("click", event => {
    setDrawer(drawer, overlay, true);
    event.currentTarget.setAttribute("aria-expanded", "true");
  });
  qs("[data-menu-close]")?.addEventListener("click", () => {
    setDrawer(drawer, overlay, false);
    qs("[data-menu-open]")?.focus();
  });
  overlay?.addEventListener("click", () => {
    setDrawer(drawer, overlay, false);
    filters?.classList.remove("open");
    qs("[data-filter-toggle]")?.setAttribute("aria-expanded", "false");
  });
  document.addEventListener("keydown", event => {
    if (event.key === "Escape" && drawer?.classList.contains("open")) {
      setDrawer(drawer, overlay, false);
      qs("[data-menu-open]")?.focus();
    }
    if (event.key === "Tab" && drawer?.classList.contains("open")) {
      const focusable = qsa("a, button, input, select, textarea, [tabindex]:not([tabindex='-1'])", drawer)
        .filter(element => !element.disabled && !element.hidden);
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
  });

  const searchDialog = qs("[data-search-dialog]");
  qs("[data-search-open]")?.addEventListener("click", () => {
    if (typeof searchDialog?.showModal === "function") searchDialog.showModal();
    qs("input[type=search]", searchDialog)?.focus();
  });
  qs("[data-search-close]")?.addEventListener("click", () => searchDialog?.close());

  qsa("[data-flash-message]").forEach(message => {
    qs("button", message)?.addEventListener("click", () => message.remove());
    window.setTimeout(() => message.remove(), 6000);
  });

  function toast(message, isError = false) {
    const region = qs(".toast-region");
    if (!region) return;
    const element = document.createElement("div");
    element.className = `toast${isError ? " error" : ""}`;
    element.textContent = message;
    region.append(element);
    window.setTimeout(() => element.remove(), 3800);
  }

  qsa("[data-quantity]").forEach(wrapper => {
    const input = qs("input", wrapper);
    const update = delta => {
      const min = Number(input.min || 1);
      const max = Number(input.max || 9999);
      input.value = Math.min(max, Math.max(min, Number(input.value || min) + delta));
      input.dispatchEvent(new Event("change", { bubbles: true }));
    };
    qs("[data-qty-plus]", wrapper)?.addEventListener("click", () => update(1));
    qs("[data-qty-minus]", wrapper)?.addEventListener("click", () => update(-1));
  });

  qsa("[data-variant-form]").forEach(form => {
    const select = qs("[data-variant-select]", form);
    if (!select) return;
    const quantity = qs("input[name=quantity]", form);
    const price = qs("[data-variant-price]") || qs(".detail-price strong");
    const stockLine = qs("[data-stock-line]");
    select.addEventListener("change", () => {
      const option = select.selectedOptions[0];
      const stock = Number(option?.dataset.stock || 0);
      if (quantity) {
        quantity.max = String(Math.max(stock, 1));
        quantity.value = "1";
      }
      if (price && option?.dataset.price) price.textContent = `${option.dataset.price} ج.م`;
      if (stockLine && select.value) stockLine.textContent = stock ? `متوفر الآن — ${stock} قطعة` : "غير متوفر حاليًا";
    });
  });

  async function postForm(form) {
    const response = await fetch(form.action, {
      method: "POST",
      body: new FormData(form),
      headers: { "X-Requested-With": "XMLHttpRequest" },
      credentials: "same-origin"
    });
    const contentType = response.headers.get("content-type") || "";
    const data = contentType.includes("application/json")
      ? await response.json()
      : { message: response.status === 429 ? "محاولات كثيرة. حاول بعد قليل." : "انتهت الجلسة أو حدث خطأ. حدّث الصفحة وحاول مرة أخرى." };
    if (!response.ok) throw new Error(data.message || "حدث خطأ. حاول مرة أخرى.");
    return data;
  }

  qsa("[data-ajax-cart]").forEach(form => form.addEventListener("submit", async event => {
    event.preventDefault();
    const button = qs("button[type=submit]", form);
    button.disabled = true;
    try {
      const data = await postForm(form);
      qsa("[data-cart-count]").forEach(badge => badge.textContent = data.cart_count);
      toast(data.message);
    } catch (error) {
      toast(error.message, true);
    } finally {
      button.disabled = false;
    }
  }));

  qsa("[data-ajax-wishlist]").forEach(form => form.addEventListener("submit", async event => {
    event.preventDefault();
    const button = qs("button", form);
    button.disabled = true;
    try {
      const data = await postForm(form);
      button.classList.toggle("active", data.active);
      button.setAttribute("aria-pressed", String(data.active));
      const label = qs("[data-wishlist-label]", button);
      if (label) label.textContent = data.active ? "في المفضلة" : "أضيفي للمفضلة";
      const accessibleLabel = data.active ? button.dataset.removeLabel : button.dataset.addLabel;
      if (accessibleLabel) button.setAttribute("aria-label", accessibleLabel);
      toast(data.message);
    } catch (error) {
      toast(error.message, true);
    } finally {
      button.disabled = false;
    }
  }));

  const gallery = qs("[data-gallery]");
  if (gallery) {
    const main = qs("[data-gallery-main]", gallery);
    qsa("[data-gallery-thumb]", gallery).forEach(thumb => thumb.addEventListener("click", () => {
      main.src = thumb.dataset.galleryThumb;
      qsa("[data-gallery-thumb]", gallery).forEach(item => item.classList.remove("active"));
      thumb.classList.add("active");
    }));
  }

  const filters = qs("[data-filters]");
  qs("[data-filter-toggle]")?.addEventListener("click", () => {
    filters?.classList.add("open");
    document.body.classList.add("drawer-open");
    if (overlay) overlay.hidden = false;
    qs("[data-filter-toggle]")?.setAttribute("aria-expanded", "true");
    qs("button, input, select", filters)?.focus();
  });
  qs("[data-filter-close]")?.addEventListener("click", () => {
    filters?.classList.remove("open");
    document.body.classList.remove("drawer-open");
    if (overlay) overlay.hidden = true;
    qs("[data-filter-toggle]")?.setAttribute("aria-expanded", "false");
    qs("[data-filter-toggle]")?.focus();
  });

  const checkout = qs("[data-checkout]");
  if (checkout) {
    const paymentRadios = qsa("input[name=payment_method]", checkout);
    const instapay = qs("[data-instapay]", checkout);
    const receipt = qs("input[name=payment_receipt]", checkout);
    const syncPayment = () => {
      const selected = qs("input[name=payment_method]:checked", checkout)?.value;
      const show = selected === "instapay";
      instapay.hidden = !show;
      if (receipt) receipt.required = show;
    };
    paymentRadios.forEach(radio => radio.addEventListener("change", syncPayment));
    syncPayment();

    receipt?.addEventListener("change", () => {
      const preview = qs("[data-receipt-preview]", checkout);
      preview.replaceChildren();
      const file = receipt.files?.[0];
      if (!file) return;
      const name = document.createElement("p");
      name.textContent = file.name;
      preview.append(name);
      if (file.type.startsWith("image/")) {
        const image = document.createElement("img");
        image.alt = "معاينة إثبات التحويل";
        image.src = URL.createObjectURL(file);
        preview.append(image);
      }
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "text-btn";
      remove.textContent = "إزالة الصورة واختيار أخرى";
      remove.addEventListener("click", () => {
        receipt.value = "";
        preview.replaceChildren();
      });
      preview.append(remove);
    });

    const zone = qs("select[name=governorate]", checkout);
    zone?.addEventListener("change", async () => {
      if (!zone.value) return;
      try {
        const url = `${checkout.dataset.shippingUrl}?zone=${encodeURIComponent(zone.value)}`;
        const response = await fetch(url, { credentials: "same-origin" });
        if (!response.ok) throw new Error();
        const data = await response.json();
        qs("[data-shipping-cost]", checkout).textContent = `${data.shipping} ج.م`;
        qs("[data-order-total]", checkout).textContent = data.total;
        qs("[data-instapay-total]", checkout).textContent = data.total;
        const estimate = qs("[data-delivery-estimate]", checkout);
        if (estimate) estimate.textContent = `التوصيل المتوقع خلال ${data.delivery_min_days}–${data.delivery_max_days} أيام عمل.`;
      } catch {
        toast("تعذر تحديث الشحن. اختاري المحافظة مرة أخرى.", true);
      }
    });

    checkout.addEventListener("submit", () => {
      const submit = qs("[data-checkout-submit]", checkout);
      if (!submit) return;
      submit.disabled = true;
      submit.textContent = "جارٍ تثبيت طلبك…";
    });
  }

  qsa("form[data-confirm]").forEach(form => form.addEventListener("submit", event => {
    if (!window.confirm(form.dataset.confirm)) event.preventDefault();
  }));

  const dashboardSidebar = qs("[data-dashboard-sidebar]");
  qs("[data-dashboard-open]")?.addEventListener("click", () => {
    dashboardSidebar?.classList.add("open");
    document.body.classList.add("drawer-open");
  });
  qs("[data-dashboard-close]")?.addEventListener("click", () => {
    dashboardSidebar?.classList.remove("open");
    document.body.classList.remove("drawer-open");
  });
  document.addEventListener("keydown", event => {
    if (event.key === "Escape" && dashboardSidebar?.classList.contains("open")) {
      dashboardSidebar.classList.remove("open");
      document.body.classList.remove("drawer-open");
      qs("[data-dashboard-open]")?.focus();
    }
  });
})();
