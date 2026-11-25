for (const form of document.querySelectorAll("form[data-confirm]")) {
  form.addEventListener("submit", (event) => {
    if (!window.confirm(form.dataset.confirm)) event.preventDefault();
  });
}

const copyButton = document.querySelector("#copy-caption");
if (copyButton && navigator.clipboard) {
  copyButton.hidden = false;
  copyButton.addEventListener("click", async () => {
    const caption = document.querySelector("#caption");
    const status = document.querySelector("#copy-status");
    try {
      await navigator.clipboard.writeText(caption.value);
      status.textContent = "Caption copied.";
    } catch {
      caption.select();
      status.textContent = "Caption selected. Use your keyboard or device to copy it.";
    }
  });
}
