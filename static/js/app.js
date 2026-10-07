document.addEventListener("submit", (event) => {
    const form = event.target.closest("[data-confirm]");
    if (form && !window.confirm(form.dataset.confirm)) event.preventDefault();
});

document.addEventListener("click", async (event) => {
    const removeButton = event.target.closest(".remove-row");
    if (removeButton) {
        const row = removeButton.closest(".ingredient-row, .day-recipe-row, .shopping-recipe-row");
        if (row) row.remove();
    }

    if (event.target.closest("#add-ingredient")) {
        const template = document.querySelector("#ingredient-row-template");
        document.querySelector("#ingredient-rows").append(template.content.cloneNode(true));
    }

    const dayButton = event.target.closest(".add-day-recipe");
    if (dayButton) {
        const template = document.getElementById(dayButton.dataset.template);
        document.getElementById(dayButton.dataset.list).append(template.content.cloneNode(true));
    }

    if (event.target.closest("#add-shopping-recipe")) {
        const template = document.querySelector("#shopping-recipe-template");
        document.querySelector("#shopping-recipe-rows").append(template.content.cloneNode(true));
    }

    const copyButton = event.target.closest("#copy-plan-link");
    if (copyButton) {
        try {
            await navigator.clipboard.writeText(copyButton.dataset.url);
            copyButton.textContent = "Copied!";
            window.setTimeout(() => { copyButton.textContent = "Copy short link"; }, 1800);
        } catch {
            window.prompt("Copy this plan link:", copyButton.dataset.url);
        }
    }
});