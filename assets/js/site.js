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
