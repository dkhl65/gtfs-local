document.addEventListener("DOMContentLoaded", function () {
  const transfers = document.getElementById("transfers");
  const addTransferButton = document.getElementById("add-transfer");
  const removeTransferButton = document.getElementById("remove-transfer");

  function renumberTransfers() {
    const transferBlocks = transfers.querySelectorAll("[data-transfer]");
    removeTransferButton.hidden = transferBlocks.length === 1;

    transferBlocks.forEach(function (transfer, index) {
      const transferNumber = index + 1;
      transfer.querySelector("[data-transfer-title]").textContent = `Transfer ${transferNumber}`;

      transfer.querySelectorAll("[id]").forEach(function (field) {
        if (field.id) {
          const previousId = field.id;
          const nextId = previousId.replace(/\d+(?=[a-z]?$)/, transferNumber);
          const label = transfer.querySelector(`label[for="${previousId}"]`);
          field.id = nextId;
          field.name = field.name.replace(/\d+(?=[a-z]?$)/, transferNumber);
          if (label) {
            label.htmlFor = nextId;
          }
        }
      });
    });
  }

  function removeTransfer() {
    transfers.lastElementChild.remove();
    renumberTransfers();
  }

  addTransferButton.addEventListener("click", function () {
    const firstTransfer = transfers.querySelector("[data-transfer]");
    const newTransfer = firstTransfer.cloneNode(true);

    newTransfer.querySelectorAll("select").forEach(function (select) {
      select.selectedIndex = 0;
    });
    transfers.appendChild(newTransfer);
    renumberTransfers();
  });

  removeTransferButton.addEventListener("click", removeTransfer);
  renumberTransfers();
});
