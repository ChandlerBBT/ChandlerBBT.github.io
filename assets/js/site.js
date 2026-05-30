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
