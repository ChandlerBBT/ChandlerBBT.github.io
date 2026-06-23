const searchInput = document.querySelector("[data-search]");
const postList = document.querySelector("[data-post-list]");
const filterButtons = Array.from(document.querySelectorAll("[data-filter]"));

function applyFilters() {
  if (!postList) return;
  const query = (searchInput?.value || "").trim().toLowerCase();
  const active = document.querySelector(".filter-chip.active")?.dataset.filter || "";

  for (const card of postList.querySelectorAll(".post-card")) {
    const haystack = `${card.dataset.title || ""} ${card.dataset.tags || ""}`;
    const matchesSearch = !query || haystack.includes(query);
    const matchesTag = !active || haystack.includes(active);
    card.classList.toggle("is-hidden", !(matchesSearch && matchesTag));
  }
}

searchInput?.addEventListener("input", applyFilters);

for (const button of filterButtons) {
  button.addEventListener("click", () => {
    for (const item of filterButtons) item.classList.remove("active");
    button.classList.add("active");
    applyFilters();
  });
}

function closeLightbox() {
  document.querySelector(".image-lightbox")?.remove();
  document.body.classList.remove("has-lightbox");
}

function openLightbox(image) {
  closeLightbox();
  const overlay = document.createElement("button");
  overlay.type = "button";
  overlay.className = "image-lightbox";
  overlay.setAttribute("aria-label", "关闭放大图片");

  const enlarged = document.createElement("img");
  enlarged.src = image.currentSrc || image.src;
  enlarged.alt = image.alt || "";
  overlay.append(enlarged);

  overlay.addEventListener("click", closeLightbox);
  document.body.append(overlay);
  document.body.classList.add("has-lightbox");
  overlay.focus();
}

for (const image of document.querySelectorAll(".article-shell img, .tutorial-page img")) {
  image.tabIndex = 0;
  image.setAttribute("role", "button");
  image.addEventListener("click", () => openLightbox(image));
  image.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      openLightbox(image);
    }
  });
}

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeLightbox();
});

async function copyText(text) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }

  const field = document.createElement("textarea");
  field.value = text;
  field.setAttribute("readonly", "");
  field.style.position = "fixed";
  field.style.top = "-9999px";
  field.style.opacity = "0";
  document.body.append(field);
  field.select();
  const copied = document.execCommand("copy");
  field.remove();
  if (!copied) throw new Error("Copy command failed");
}

function showCodeCopyToast(wrapper, message) {
  const toast = wrapper.querySelector(".code-copy-toast");
  if (!toast) return;
  window.clearTimeout(Number(toast.dataset.timer || 0));
  toast.textContent = message;
  toast.classList.add("is-visible");
  toast.dataset.timer = String(window.setTimeout(() => {
    toast.classList.remove("is-visible");
  }, 1400));
}

function setupCodeCopyButtons() {
  const codeBlocks = document.querySelectorAll(".article-body pre, .tutorial-content pre");
  for (const pre of codeBlocks) {
    if (pre.closest(".code-block-wrap")) continue;
    const code = pre.querySelector("code") || pre;
    const wrapper = document.createElement("div");
    wrapper.className = "code-block-wrap";
    pre.before(wrapper);
    wrapper.append(pre);

    const button = document.createElement("button");
    button.type = "button";
    button.className = "code-copy-button";
    button.setAttribute("aria-label", "复制代码");
    button.setAttribute("title", "复制代码");
    button.innerHTML = '<span aria-hidden="true"></span>';

    const toast = document.createElement("span");
    toast.className = "code-copy-toast";
    toast.setAttribute("role", "status");
    toast.setAttribute("aria-live", "polite");

    button.addEventListener("click", async () => {
      try {
        await copyText(code.innerText.replace(/\n+$/g, ""));
        showCodeCopyToast(wrapper, "已复制代码");
      } catch {
        showCodeCopyToast(wrapper, "复制失败");
      }
    });

    wrapper.append(button, toast);
  }
}

function setupCodeTabs() {
  for (const group of document.querySelectorAll("[data-code-tabs]")) {
    const tabs = Array.from(group.querySelectorAll('[role="tab"]'));
    const panels = Array.from(group.querySelectorAll('[role="tabpanel"]'));
    if (!tabs.length || !panels.length) continue;

    function activate(tab) {
      const targetId = tab.getAttribute("aria-controls");
      for (const item of tabs) {
        const active = item === tab;
        item.classList.toggle("is-active", active);
        item.setAttribute("aria-selected", String(active));
        item.tabIndex = active ? 0 : -1;
      }
      for (const panel of panels) {
        const active = panel.id === targetId;
        panel.classList.toggle("is-active", active);
        panel.hidden = !active;
      }
    }

    for (const tab of tabs) {
      tab.addEventListener("click", () => activate(tab));
      tab.addEventListener("keydown", (event) => {
        if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
        event.preventDefault();
        const current = tabs.indexOf(tab);
        let next = current;
        if (event.key === "ArrowLeft") next = (current - 1 + tabs.length) % tabs.length;
        if (event.key === "ArrowRight") next = (current + 1) % tabs.length;
        if (event.key === "Home") next = 0;
        if (event.key === "End") next = tabs.length - 1;
        tabs[next].focus();
        activate(tabs[next]);
      });
    }
  }
}

function buildArticleToc() {
  const articleShell = document.querySelector(".article-shell");
  const articleBody = document.querySelector(".article-body");
  if (!articleShell || !articleBody) return;

  const headings = Array.from(articleBody.querySelectorAll("h2, h3"));
  if (headings.length < 3) return;

  const toc = document.createElement("aside");
  toc.className = "article-toc";
  toc.setAttribute("aria-label", "文章目录");

  const title = document.createElement("div");
  title.className = "article-toc-title";
  title.textContent = "阅读路径";

  const nav = document.createElement("nav");
  nav.className = "article-toc-links";

  const records = headings.map((heading, index) => {
    if (!heading.id) heading.id = `section-${index + 1}`;
    const link = document.createElement("a");
    link.href = `#${heading.id}`;
    link.textContent = heading.textContent.trim();
    link.dataset.target = heading.id;
    if (heading.tagName.toLowerCase() === "h3") link.classList.add("is-subsection");
    nav.append(link);
    return { heading, link };
  });

  function updateActiveLink() {
    const current = [...records]
      .reverse()
      .find((record) => record.heading.getBoundingClientRect().top <= 112);
    for (const record of records) {
      record.link.classList.toggle("active", record === current);
    }
  }

  toc.append(title, nav);
  const cover = articleShell.querySelector(".article-cover");
  if (cover) {
    cover.after(toc);
  } else {
    articleShell.prepend(toc);
  }
  document.body.classList.add("has-floating-toc");
  updateActiveLink();
  window.addEventListener("scroll", updateActiveLink, { passive: true });
}

function setupTutorialSidebar() {
  const sidebar = document.querySelector(".tutorial-sidebar");
  if (!sidebar) return;

  function setToggleOpen(toggle, isOpen) {
    const panelId = toggle.getAttribute("aria-controls");
    const panel = panelId ? document.getElementById(panelId) : null;
    const item = toggle.closest(".sidebar-item");
    if (!panel || !item) return;
    item.classList.toggle("is-open", isOpen);
    panel.hidden = !isOpen;
    toggle.setAttribute("aria-expanded", String(isOpen));
    toggle.setAttribute(
      "aria-label",
      `${isOpen ? "收起" : "展开"}${item.querySelector(".sidebar-page-link")?.textContent?.trim() || "当前章节"}二级目录`,
    );
  }

  function samePageHashTarget(link) {
    const url = new URL(link.href, window.location.href);
    if (url.pathname !== window.location.pathname || !url.hash) return null;
    const rawId = url.hash.slice(1);
    let id = rawId;
    try {
      id = decodeURIComponent(rawId);
    } catch {
      id = rawId;
    }
    return document.getElementById(id);
  }

  function scrollToSection(target) {
    const headerBottom = document.querySelector(".site-header")?.getBoundingClientRect().bottom || 0;
    const top = target.getBoundingClientRect().top + window.scrollY - headerBottom - 16;
    const root = document.documentElement;
    const previousScrollBehavior = root.style.scrollBehavior;
    root.style.scrollBehavior = "auto";
    window.scrollTo({ top: Math.max(0, top), behavior: "auto" });
    root.style.scrollBehavior = previousScrollBehavior;
  }

  function settleOnSection(target) {
    scrollToSection(target);
    window.requestAnimationFrame(() => scrollToSection(target));
    window.setTimeout(() => scrollToSection(target), 80);
  }

  const toggles = Array.from(sidebar.querySelectorAll(".sidebar-toggle"));
  for (const toggle of toggles) {
    setToggleOpen(toggle, toggle.getAttribute("aria-expanded") !== "false");
    toggle.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      setToggleOpen(toggle, toggle.getAttribute("aria-expanded") !== "true");
    });
  }

  const actionButtons = Array.from(sidebar.querySelectorAll("[data-sidebar-action]"));
  for (const button of actionButtons) {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      const isOpen = button.dataset.sidebarAction === "expand";
      for (const toggle of toggles) setToggleOpen(toggle, isOpen);
    });
  }

  sidebar.addEventListener("click", (event) => {
    if (!(event.target instanceof Element)) return;

    const link = event.target.closest("a.section-link");
    if (link && sidebar.contains(link)) {
      const target = samePageHashTarget(link);
      if (target) {
        event.preventDefault();
        window.history.pushState(null, "", link.hash);
        settleOnSection(target);
      }
      return;
    }
  }, { capture: true });
}

buildArticleToc();
setupTutorialSidebar();
setupCodeTabs();
setupCodeCopyButtons();
