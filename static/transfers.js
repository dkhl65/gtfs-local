document.addEventListener("DOMContentLoaded", function () {
  const transfers = document.getElementById("transfers");
  const addTransferButton = document.getElementById("add-transfer");
  const removeTransferButton = document.getElementById("remove-transfer");

  function bindRouteControls(elementIndex) {
    const agencySelect = document.getElementById("agency" + elementIndex);
    const routeSelect = document.getElementById("route" + elementIndex);
    const routesByAgency = JSON.parse(agencySelect.dataset.routes);

    agencySelect.onchange = function () {
      updateRoutes(routesByAgency, elementIndex);
    };

    routeSelect.onchange = function () {
      updateDirectionOptions(elementIndex);
    };
  }

  function renumberTransfers() {
    const transferBlocks = transfers.querySelectorAll("[data-transfer]");
    removeTransferButton.hidden = transferBlocks.length === 1;

    transferBlocks.forEach(function (transfer, index) {
      const transferNumber = index + 1;
      const isLastTransfer = index === transferBlocks.length - 1;
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

      const endingAtSelect = transfer.querySelector('select[id^="stop"][id$="b"]');
      if (endingAtSelect) {
        endingAtSelect.required = !isLastTransfer;
        const endingAtLabel = transfer.querySelector(`label[for="${endingAtSelect.id}"]`);
        if (endingAtLabel) {
          endingAtLabel.textContent = isLastTransfer ? "Ending at" : "Ending at *";
        }
      }

      bindRouteControls(transferNumber);
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
  bindRouteControls(0);
  renumberTransfers();
});
