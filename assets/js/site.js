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

for (const image of document.querySelectorAll(".article-shell img")) {
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

function buildArticleToc() {
  const articleShell = document.querySelector(".article-shell");
  const articleBody = document.querySelector(".article-body");
  if (!articleShell || !articleBody) return;

  const headings = Array.from(articleBody.querySelectorAll("h2"));
  if (headings.length < 3) return;

  const records = headings.map((heading, index) => {
    if (!heading.id) heading.id = `section-${index + 1}`;
    const text = heading.textContent.trim();
    const role = /用户|具体事情/.test(text) ? "user" : "deployer";
    return { heading, id: heading.id, text, role };
  });

  const roleLabels = {
    deployer: "部署者",
    user: "用户",
  };
  let activeRole = "deployer";

  const toc = document.createElement("aside");
  toc.className = "article-toc";
  toc.setAttribute("aria-label", "文章目录");

  const title = document.createElement("div");
  title.className = "article-toc-title";
  title.textContent = "阅读路径";

  const switcher = document.createElement("div");
  switcher.className = "article-toc-switcher";

  const nav = document.createElement("nav");
  nav.className = "article-toc-links";

  function jumpToHeading(heading) {
    const previousBehavior = document.documentElement.style.scrollBehavior;
    document.documentElement.style.scrollBehavior = "auto";
    const offset = window.innerWidth <= 640 ? 132 : 96;
    const jump = () => {
      const top = heading.getBoundingClientRect().top + window.scrollY - offset;
      window.scrollTo(0, Math.max(0, top));
      updateActiveLink();
    };
    jump();
    window.setTimeout(jump, 450);
    window.setTimeout(() => {
      jump();
      document.documentElement.style.scrollBehavior = previousBehavior;
    }, 1200);
  }

  function renderLinks() {
    nav.replaceChildren();
    for (const record of records.filter((item) => item.role === activeRole)) {
      const link = document.createElement("a");
      link.href = `#${record.id}`;
      link.textContent = record.text;
      link.dataset.target = record.id;
      link.addEventListener("click", (event) => {
        event.preventDefault();
        activeRole = record.role;
        renderControls();
        jumpToHeading(record.heading);
        history.replaceState(null, "", `#${record.id}`);
      });
      nav.append(link);
    }
  }

  function renderControls() {
    switcher.replaceChildren();
    for (const [role, label] of Object.entries(roleLabels)) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = label;
      button.className = role === activeRole ? "active" : "";
      button.addEventListener("click", () => {
        activeRole = role;
        renderControls();
        const first = records.find((record) => record.role === role);
        if (first) jumpToHeading(first.heading);
      });
      switcher.append(button);
    }
    renderLinks();
  }

  function updateActiveLink() {
    const current = [...records]
      .reverse()
      .find((record) => record.heading.getBoundingClientRect().top <= 112);
    for (const link of nav.querySelectorAll("a")) {
      link.classList.toggle("active", link.dataset.target === current?.id);
    }
  }

  toc.append(title, switcher, nav);
  const cover = articleShell.querySelector(".article-cover");
  if (cover) {
    cover.after(toc);
  } else {
    articleShell.prepend(toc);
  }
  document.body.classList.add("has-floating-toc");
  renderControls();
  updateActiveLink();
  window.addEventListener("scroll", updateActiveLink, { passive: true });
}

buildArticleToc();
