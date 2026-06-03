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

buildArticleToc();
