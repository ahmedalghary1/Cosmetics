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
  const filters = qs("[data-filters]");
  const filterToggle = qs("[data-filter-toggle]");

  function setFilters(open, restoreFocus = false) {
    if (!filters) return;
    filters.classList.toggle("open", open);
    document.body.classList.toggle("drawer-open", open);
    if (overlay) overlay.hidden = !open;
    filterToggle?.setAttribute("aria-expanded", String(open));
    if (open) {
      qs("button, input, select", filters)?.focus();
    } else if (restoreFocus) {
      filterToggle?.focus();
    }
  }

  qs("[data-menu-open]")?.addEventListener("click", event => {
    setDrawer(drawer, overlay, true);
    event.currentTarget.setAttribute("aria-expanded", "true");
  });
  qs("[data-menu-close]")?.addEventListener("click", () => {
    setDrawer(drawer, overlay, false);
    qs("[data-menu-open]")?.focus();
  });
  overlay?.addEventListener("click", () => {
    const filtersWereOpen = filters?.classList.contains("open");
    setDrawer(drawer, overlay, false);
    setFilters(false, Boolean(filtersWereOpen));
  });
  document.addEventListener("keydown", event => {
    if (event.key === "Escape" && filters?.classList.contains("open")) {
      setFilters(false, true);
      return;
    }
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

  const cartPage = qs("[data-cart-page]");
  if (cartPage) {
    const currency = cartPage.dataset.currency || "ج.م";
    const pendingUpdates = new WeakMap();
    const renderAmount = value => `${value} ${currency}`;

    async function updateCartLine(form) {
      const input = qs("input[name=quantity]", form);
      const button = qs("button[type=submit]", form);
      const quantityButtons = qsa("[data-qty-plus], [data-qty-minus]", form);
      const acceptedQuantity = input.dataset.acceptedValue || input.defaultValue;
      button.disabled = true;
      input.readOnly = true;
      quantityButtons.forEach(control => { control.disabled = true; });
      form.setAttribute("aria-busy", "true");
      try {
        const data = await postForm(form);
        input.dataset.acceptedValue = String(data.quantity);
        qsa("[data-cart-count]").forEach(badge => badge.textContent = data.cart_count);
        qs("[data-cart-line-total]", form.closest(".cart-item")).textContent = renderAmount(data.line_total);
        qs("[data-cart-subtotal]", cartPage).textContent = renderAmount(data.subtotal);
        const discount = qs("[data-cart-discount]", cartPage);
        if (discount) discount.textContent = `− ${renderAmount(data.discount)}`;
        qs("[data-cart-total]", cartPage).textContent = renderAmount(data.total);
        if (Number(data.quantity) === 0) window.location.reload();
      } catch (error) {
        input.value = acceptedQuantity;
        toast(error.message, true);
      } finally {
        button.disabled = false;
        input.readOnly = false;
        quantityButtons.forEach(control => { control.disabled = false; });
        form.removeAttribute("aria-busy");
      }
    }

    qsa("[data-cart-update]", cartPage).forEach(form => {
      const input = qs("input[name=quantity]", form);
      input.dataset.acceptedValue = input.value;
      const submitUpdate = () => {
        window.clearTimeout(pendingUpdates.get(form));
        pendingUpdates.delete(form);
        updateCartLine(form);
      };
      form.addEventListener("submit", event => {
        event.preventDefault();
        submitUpdate();
      });
      input.addEventListener("change", () => {
        window.clearTimeout(pendingUpdates.get(form));
        pendingUpdates.set(form, window.setTimeout(submitUpdate, 180));
      });
    });
  }

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

  filterToggle?.addEventListener("click", () => setFilters(true));
  qs("[data-filter-close]")?.addEventListener("click", () => setFilters(false, true));
  window.addEventListener("resize", () => {
    if (window.innerWidth >= 850 && filters?.classList.contains("open")) {
      setFilters(false);
    }
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

  qsa("[data-choice-picker]").forEach(picker => {
    const search = qs("[data-choice-search]", picker);
    const choices = qsa('input[type="checkbox"]', picker);
    const rows = choices.map(choice => choice.closest("label")?.parentElement || choice.closest("label"));
    const count = qs("[data-choice-count]", picker);
    const updateCount = () => {
      const selected = choices.filter(choice => choice.checked).length;
      if (count) count.textContent = selected ? `تم اختيار ${selected}` : "لم يتم اختيار عناصر";
    };
    const filterChoices = () => {
      const query = (search?.value || "").trim().toLocaleLowerCase("ar");
      rows.forEach(row => {
        if (row) row.hidden = Boolean(query) && !row.textContent.toLocaleLowerCase("ar").includes(query);
      });
    };
    search?.addEventListener("input", filterChoices);
    choices.forEach(choice => choice.addEventListener("change", updateCount));
    qs("[data-choice-all]", picker)?.addEventListener("click", () => {
      choices.forEach((choice, index) => {
        if (!rows[index]?.hidden && !choice.disabled) choice.checked = true;
      });
      updateCount();
    });
    qs("[data-choice-clear]", picker)?.addEventListener("click", () => {
      choices.forEach(choice => { if (!choice.disabled) choice.checked = false; });
      updateCount();
    });
    updateCount();
  });

  const dashboardSidebar = qs("[data-dashboard-sidebar]");
  const dashboardOverlay = qs("[data-dashboard-overlay]");
  function setDashboardSidebar(open, restoreFocus = false) {
    dashboardSidebar?.classList.toggle("open", open);
    if (dashboardOverlay) dashboardOverlay.hidden = !open;
    document.body.classList.toggle("drawer-open", open);
    qs("[data-dashboard-open]")?.setAttribute("aria-expanded", String(open));
    if (open) qs("[data-dashboard-close]", dashboardSidebar)?.focus();
    else if (restoreFocus) qs("[data-dashboard-open]")?.focus();
  }
  qs("[data-dashboard-open]")?.addEventListener("click", () => {
    setDashboardSidebar(true);
  });
  qs("[data-dashboard-close]")?.addEventListener("click", () => {
    setDashboardSidebar(false, true);
  });
  dashboardOverlay?.addEventListener("click", () => setDashboardSidebar(false, true));
  document.addEventListener("keydown", event => {
    if (event.key === "Escape" && dashboardSidebar?.classList.contains("open")) {
      setDashboardSidebar(false, true);
    }
  });
  window.addEventListener("resize", () => {
    if (window.innerWidth >= 850 && dashboardSidebar?.classList.contains("open")) {
      setDashboardSidebar(false);
    }
  });

  function initScrollMotion() {
    const motionPreference = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (motionPreference.matches || !("IntersectionObserver" in window)) return;

    const revealSelectors = [
      ".hero-content > *",
      ".page-hero .container > *",
      ".section-heading > *",
      ".category-row > *",
      ".product-grid > *",
      ".bundle-offers-grid > *",
      ".routine-grid > *",
      ".social-grid > *",
      ".trust-strip .container > *",
      ".promo-banner > div > *",
      ".product-detail-grid > *",
      ".product-description > *",
      ".shop-layout > *",
      ".cart-layout > *",
      ".checkout-layout > *",
      ".account-layout > *",
      ".orders-list > *",
      ".form-grid > *",
      ".success-page > *",
      ".error-page > *",
      ".site-footer .footer-grid > *",
      ".site-footer .footer-bottom > *"
    ];
    const scaleSelectors = ".category-row > *, .product-grid > *, .bundle-offers-grid > *, .routine-grid > *, .social-grid > *, .product-detail-grid > .gallery";
    const revealElements = [...new Set(revealSelectors.flatMap(selector => qsa(selector)))]
      .filter(element => !element.closest(".dashboard-body"));
    const groupIndexes = new Map();

    revealElements.forEach(element => {
      const parent = element.parentElement;
      const index = groupIndexes.get(parent) || 0;
      groupIndexes.set(parent, index + 1);
      element.classList.add("scroll-reveal");
      if (element.matches(scaleSelectors)) element.classList.add("scroll-reveal-scale");
      element.style.setProperty("--reveal-delay", `${Math.min(index, 5) * 55}ms`);
      element.style.setProperty("--reveal-distance", `${18 + (index % 3) * 3}px`);
    });

    qsa(".promo-banner, .about-content, .empty-state").forEach(element => {
      if (element.closest(".dashboard-body") || element.classList.contains("scroll-reveal")) return;
      element.classList.add("scroll-reveal", "scroll-reveal-scale");
    });

    const allRevealElements = qsa(".scroll-reveal");
    const revealObserver = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (!entry.isIntersecting) return;
        const element = entry.target;
        element.classList.add("is-visible");
        revealObserver.unobserve(element);
        let finished = false;
        const finishReveal = () => {
          if (finished) return;
          finished = true;
          element.classList.remove("scroll-reveal", "scroll-reveal-scale", "is-visible");
          element.style.removeProperty("--reveal-delay");
          element.style.removeProperty("--reveal-distance");
          element.removeEventListener("transitionend", onTransitionEnd);
        };
        const onTransitionEnd = event => {
          if (event.propertyName === "transform") finishReveal();
        };
        element.addEventListener("transitionend", onTransitionEnd);
        window.setTimeout(finishReveal, 1250);
      });
    }, {
      threshold: 0.12,
      rootMargin: "0px 0px -7% 0px"
    });
    allRevealElements.forEach(element => revealObserver.observe(element));

    const parallaxElements = [
      [qs(".hero-bg"), 18],
      [qs(".promo-banner > img"), 13],
      [qs(".gallery-main img"), 8]
    ].filter(([element]) => element);
    const activeParallax = new Set();
    let frameRequested = false;

    parallaxElements.forEach(([element, speed]) => {
      element.classList.add("scroll-parallax");
      element.dataset.parallaxSpeed = String(speed);
    });

    const renderParallax = () => {
      frameRequested = false;
      const viewportHeight = window.innerHeight || 1;
      const mobileFactor = window.innerWidth < 700 ? 0.62 : 1;
      activeParallax.forEach(element => {
        const rect = element.getBoundingClientRect();
        const progress = ((rect.top + rect.height / 2) - viewportHeight / 2) / viewportHeight;
        const speed = Number(element.dataset.parallaxSpeed || 10) * mobileFactor;
        const offset = Math.max(-speed, Math.min(speed, progress * -speed));
        element.style.setProperty("--parallax-y", `${offset.toFixed(2)}px`);
      });
    };
    const requestParallaxFrame = () => {
      if (frameRequested || !activeParallax.size) return;
      frameRequested = true;
      window.requestAnimationFrame(renderParallax);
    };
    const parallaxObserver = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (entry.isIntersecting) activeParallax.add(entry.target);
        else activeParallax.delete(entry.target);
      });
      requestParallaxFrame();
    }, { rootMargin: "18% 0px" });
    parallaxElements.forEach(([element]) => parallaxObserver.observe(element));

    window.addEventListener("scroll", requestParallaxFrame, { passive: true });
    window.addEventListener("resize", requestParallaxFrame, { passive: true });
    document.documentElement.classList.add("motion-ready");

    const disableMotion = event => {
      if (!event.matches) return;
      revealObserver.disconnect();
      parallaxObserver.disconnect();
      window.removeEventListener("scroll", requestParallaxFrame);
      window.removeEventListener("resize", requestParallaxFrame);
      document.documentElement.classList.remove("motion-ready");
      allRevealElements.forEach(element => {
        element.classList.remove("scroll-reveal", "scroll-reveal-scale", "is-visible");
        element.style.removeProperty("--reveal-delay");
        element.style.removeProperty("--reveal-distance");
      });
      parallaxElements.forEach(([element]) => {
        element.classList.remove("scroll-parallax");
        element.style.removeProperty("--parallax-y");
      });
      motionPreference.removeEventListener?.("change", disableMotion);
    };
    motionPreference.addEventListener?.("change", disableMotion);
  }

  initScrollMotion();
})();
