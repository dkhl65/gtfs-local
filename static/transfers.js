document.addEventListener("DOMContentLoaded", function () {
  const transfers = document.getElementById("transfers");
  const addTransferButton = document.getElementById("add-transfer");
  const removeTransferButton = document.getElementById("remove-transfer");

  function bindRouteControls(elementIndex) {
    const agencySelect = document.getElementById("agency" + elementIndex);
    const routeSelect = document.getElementById("route" + elementIndex);
    const directionSelect = document.getElementById("direction" + elementIndex);
    const startingAtSelect = document.getElementById("stop" + elementIndex + "a");
    const endingAtSelect = document.getElementById("stop" + elementIndex + "b");
    const routesByAgency = JSON.parse(agencySelect.dataset.routes);

    agencySelect.onchange = function () {
      updateRoutes(routesByAgency, elementIndex);
      resetStopOptions(elementIndex);
    };

    routeSelect.onchange = async function () {
      resetStopOptions(elementIndex);
      await updateDirectionOptions(elementIndex);
      updateStopOptions(elementIndex);
    };

    directionSelect.onchange = function () {
      updateStopOptions(elementIndex);
    };

    startingAtSelect.onchange = function () {
      updateBoundStopOptions(elementIndex);
    };

    endingAtSelect.onchange = function () {
      updateBoundStopOptions(elementIndex);
    };
  }

  function resetStopOptions(elementIndex) {
    ["a", "b"].forEach(function (suffix) {
      const stopSelect = document.getElementById("stop" + elementIndex + suffix);
      stopSelect.innerHTML = '<option value="">-- Select a stop --</option>';
    });
  }

  function setStopOptions(stopSelect, options, placeholder) {
    const selectedValue = stopSelect.value;
    stopSelect.innerHTML = `<option value="">${placeholder}</option>`;
    options.forEach(function (optionData) {
      const option = document.createElement("option");
      option.value = optionData.value;
      option.textContent = optionData.label;
      stopSelect.appendChild(option);
    });
    if (options.some(optionData => optionData.value === selectedValue)) {
      stopSelect.value = selectedValue;
    }
  }

  function updateBoundStopOptions(elementIndex) {
    const startingAtSelect = document.getElementById("stop" + elementIndex + "a");
    const endingAtSelect = document.getElementById("stop" + elementIndex + "b");
    const options = startingAtSelect._stopOptions || [];
    const startingAt = startingAtSelect.value;
    const endingAt = endingAtSelect.value;

    setStopOptions(
      startingAtSelect,
      options.filter(optionData => !endingAt || Number(optionData.value) < Number(endingAt)),
      "-- Select a stop --"
    );
    setStopOptions(
      endingAtSelect,
      options.filter(optionData => !startingAt || Number(optionData.value) > Number(startingAt)),
      "-- Select a stop --"
    );
  }

  async function updateStopOptions(elementIndex) {
    const agency = document.getElementById("agency" + elementIndex).value;
    const route = document.getElementById("route" + elementIndex).value;
    const direction = document.getElementById("direction" + elementIndex).value;
    const date = document.getElementById("date").value;

    if (!agency || !route || !direction || !date) {
      resetStopOptions(elementIndex);
      return;
    }

    try {
      const query = new URLSearchParams({ agency, route, direction, date });
      const response = await fetch(`/stop-options?${query}`);
      const data = await response.json();
      const options = Array.isArray(data.options) ? data.options : [];
      const startingAtSelect = document.getElementById("stop" + elementIndex + "a");
      startingAtSelect._stopOptions = options;
      updateBoundStopOptions(elementIndex);
    } catch (_error) {
      resetStopOptions(elementIndex);
    }
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
  document.getElementById("date").addEventListener("change", function () {
    transfers.querySelectorAll("[data-transfer]").forEach(function (transfer, index) {
      updateStopOptions(index + 1);
    });
    updateStopOptions(0);
  });
  bindRouteControls(0);
  renumberTransfers();
});
