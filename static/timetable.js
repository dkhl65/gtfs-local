document.addEventListener("DOMContentLoaded", () => {
  const table = document.querySelector("table");
  const tbody = table ? table.querySelector("tbody") : null;
  const thead = table ? table.querySelector("thead") : null;

  if (!table || !tbody || !thead) {
    return;
  }

  const startStopSelect = document.getElementById("start-station");
  const endStopSelect = document.getElementById("end-station");
  const startHourInput = document.getElementById("start-hour");
  const startMinuteInput = document.getElementById("start-minute");
  const endHourInput = document.getElementById("end-hour");
  const endMinuteInput = document.getElementById("end-minute");
  const clearFiltersButton = document.getElementById("clear-filters");
  const omitIntermediateStopsCheckbox = document.getElementById("omit-intermediate-stops");
  const downloadLink = document.getElementById("download-link");
  const toggleFiltersButton = document.getElementById("toggle-filters");
  const filtersPanel = document.querySelector(".timetable-filters");

  if (
    !startStopSelect
    || !endStopSelect
    || !startHourInput
    || !startMinuteInput
    || !endHourInput
    || !endMinuteInput
    || !clearFiltersButton
    || !omitIntermediateStopsCheckbox
  ) {
    return;
  }

  const headerCells = Array.from(thead.querySelectorAll("th"));
  const bodyRows = Array.from(tbody.querySelectorAll("tr"));

  const tripColumnCount = Math.max(0, headerCells.length - 1);
  const baseDownloadHref = downloadLink ? downloadLink.getAttribute("href") : null;
  const defaultColumnOrder = Array.from({ length: tripColumnCount }, (_, index) => index);
  const rowModels = bodyRows.map((rowEl) => {
    const cells = Array.from(rowEl.querySelectorAll("td"));
    const stopName = cells[0] ? cells[0].textContent.trim() : "";
    const times = cells.slice(1).map((cell) => parseTableTime(cell.textContent.trim()));
    return {
      rowEl,
      stopName,
      cells,
      times
    };
  });
  const stopOptions = rowModels.map((row, index) => ({
    index,
    name: row.stopName
  }));

  const allMinutes = [];
  rowModels.forEach((row) => {
    row.times.forEach((minuteValue) => {
      if (minuteValue !== null) {
        allMinutes.push(minuteValue);
      }
    });
  });

  const minTime = allMinutes.length ? Math.min(...allMinutes) : 0;
  const maxTime = allMinutes.length ? Math.max(...allMinutes) : (24 * 60) - 1;
  const maxHour = Math.max(47, Math.floor(maxTime / 60));

  setInputBounds(startHourInput, 0, maxHour);
  setInputBounds(endHourInput, 0, maxHour);
  setInputBounds(startMinuteInput, 0, 59);
  setInputBounds(endMinuteInput, 0, 59);

  setTimeInputs(startHourInput, startMinuteInput, minTime);
  setTimeInputs(endHourInput, endMinuteInput, maxTime);

  const lastValidTimeWindow = {
    start: minTime,
    end: maxTime
  };

  renderStopOptions(startStopSelect, stopOptions, null, "-- All stops --", () => true);
  renderStopOptions(endStopSelect, stopOptions, null, "-- All stops --", () => true);

  startStopSelect.addEventListener("change", () => {
    syncStopSelections("start");
    applyFilters();
  });

  endStopSelect.addEventListener("change", () => {
    syncStopSelections("end");
    applyFilters();
  });

  omitIntermediateStopsCheckbox.addEventListener("change", () => {
    applyFilters();
  });

  clearFiltersButton.addEventListener("click", () => {
    renderStopOptions(startStopSelect, stopOptions, null, "-- All stops --", () => true);
    renderStopOptions(endStopSelect, stopOptions, null, "-- All stops --", () => true);
    setTimeInputs(startHourInput, startMinuteInput, minTime);
    setTimeInputs(endHourInput, endMinuteInput, maxTime);
    lastValidTimeWindow.start = minTime;
    lastValidTimeWindow.end = maxTime;
    omitIntermediateStopsCheckbox.checked = false;
    syncStopSelections(null);
    applyFilters();
  });

  [startHourInput, startMinuteInput].forEach((input) => {
    input.addEventListener("input", () => {
      // Allow transient values while typing; validate range on commit.
      sanitizeNumericInput(input);
    });
    input.addEventListener("change", () => {
      sanitizeAndSyncTimes("start");
      applyFilters();
    });
    input.addEventListener("blur", () => {
      sanitizeAndSyncTimes("start");
      applyFilters();
    });
  });

  [endHourInput, endMinuteInput].forEach((input) => {
    input.addEventListener("input", () => {
      // Allow transient values while typing; validate range on commit.
      sanitizeNumericInput(input);
    });
    input.addEventListener("change", () => {
      sanitizeAndSyncTimes("end");
      applyFilters();
    });
    input.addEventListener("blur", () => {
      sanitizeAndSyncTimes("end");
      applyFilters();
    });
  });

  if (toggleFiltersButton && filtersPanel) {
    toggleFiltersButton.addEventListener("click", () => {
      const isHidden = filtersPanel.classList.toggle("is-hidden");
      toggleFiltersButton.textContent = isHidden ? "Show Filters" : "Hide Filters";
    });
  }

  syncStopSelections(null);
  sanitizeAndSyncTimes(null);
  applyFilters();

  function syncStopSelections(changedField) {
    let startIndex = parseOptionIndex(startStopSelect.value, rowModels.length);
    let endIndex = parseOptionIndex(endStopSelect.value, rowModels.length);

    if (startIndex !== null && endIndex !== null && startIndex > endIndex) {
      if (changedField === "end") {
        startIndex = null;
      } else {
        endIndex = null;
      }
    }

    renderStopOptions(
      startStopSelect,
      stopOptions,
      startIndex,
      "-- All stops --",
      (index) => endIndex === null || index <= endIndex
    );
    renderStopOptions(
      endStopSelect,
      stopOptions,
      endIndex,
      "-- All stops --",
      (index) => startIndex === null || index >= startIndex
    );
  }

  function sanitizeAndSyncTimes(changedField) {
    const startHour = sanitizeNumericInput(startHourInput);
    const startMinute = sanitizeNumericInput(startMinuteInput);
    const endHour = sanitizeNumericInput(endHourInput);
    const endMinute = sanitizeNumericInput(endMinuteInput);

    const startTotal = toTotalMinutes(startHour, startMinute);
    const endTotal = toTotalMinutes(endHour, endMinute);

    if (startTotal <= endTotal) {
      lastValidTimeWindow.start = startTotal;
      lastValidTimeWindow.end = endTotal;
      return;
    }

    if (changedField === "start") {
      setTimeInputs(startHourInput, startMinuteInput, lastValidTimeWindow.start);
      return;
    }

    if (changedField === "end") {
      setTimeInputs(endHourInput, endMinuteInput, lastValidTimeWindow.end);
      return;
    }

    setTimeInputs(startHourInput, startMinuteInput, lastValidTimeWindow.start);
    setTimeInputs(endHourInput, endMinuteInput, lastValidTimeWindow.end);
  }

  function applyFilters() {
    const startIndexRaw = parseOptionIndex(startStopSelect.value, rowModels.length);
    const endIndexRaw = parseOptionIndex(endStopSelect.value, rowModels.length);

    const visibleStart = startIndexRaw !== null ? startIndexRaw : 0;
    const visibleEnd = endIndexRaw !== null ? endIndexRaw : rowModels.length - 1;
    const boundaryOnly = omitIntermediateStopsCheckbox.checked
      && startIndexRaw !== null
      && endIndexRaw !== null
      && startIndexRaw < endIndexRaw;

    const startMinutes = toTotalMinutes(
      sanitizeNumericInput(startHourInput),
      sanitizeNumericInput(startMinuteInput)
    );
    const endMinutes = toTotalMinutes(
      sanitizeNumericInput(endHourInput),
      sanitizeNumericInput(endMinuteInput)
    );

    const visibleColumns = new Array(tripColumnCount).fill(false);

    for (let col = 0; col < tripColumnCount; col += 1) {
      const selectedStartTime = startIndexRaw !== null ? rowModels[startIndexRaw].times[col] : null;
      const selectedEndTime = endIndexRaw !== null ? rowModels[endIndexRaw].times[col] : null;

      if (startIndexRaw !== null && selectedStartTime === null) {
        visibleColumns[col] = false;
        continue;
      }

      if (endIndexRaw !== null && selectedEndTime === null) {
        visibleColumns[col] = false;
        continue;
      }

      const departure = selectedStartTime !== null
        ? selectedStartTime
        : pickTripTime(col, visibleStart, visibleEnd, true);
      const arrival = selectedEndTime !== null
        ? selectedEndTime
        : pickTripTime(col, visibleStart, visibleEnd, false);

      if (departure === null || arrival === null) {
        visibleColumns[col] = false;
        continue;
      }

      const normalized = normalizeTripTimes(departure, arrival);
      visibleColumns[col] = normalized.departure >= startMinutes
        && normalized.arrival <= endMinutes
        && normalized.arrival >= normalized.departure;
    }

    const isFilteringActive = startIndexRaw !== null
      || endIndexRaw !== null
      || startMinutes > minTime
      || endMinutes < maxTime
      || omitIntermediateStopsCheckbox.checked;

    const columnOrder = isFilteringActive
      ? defaultColumnOrder.slice().sort((leftIndex, rightIndex) => {
        const leftTime = pickTripTime(leftIndex, visibleStart, visibleEnd, true);
        const rightTime = pickTripTime(rightIndex, visibleStart, visibleEnd, true);

        if (leftTime === null && rightTime === null) {
          return leftIndex - rightIndex;
        }
        if (leftTime === null) {
          return 1;
        }
        if (rightTime === null) {
          return -1;
        }
        if (leftTime !== rightTime) {
          return leftTime - rightTime;
        }
        return leftIndex - rightIndex;
      })
      : defaultColumnOrder;

    applyColumnOrder(columnOrder);

    rowModels.forEach((row, rowIndex) => {
      const inSelectedRange = rowIndex >= visibleStart && rowIndex <= visibleEnd;
      const rowVisible = inSelectedRange
        && (!boundaryOnly || rowIndex === visibleStart || rowIndex === visibleEnd);
      row.rowEl.style.display = rowVisible ? "" : "none";

      for (let col = 0; col < tripColumnCount; col += 1) {
        const cell = row.cells[col + 1];
        if (!cell) {
          continue;
        }
        cell.style.display = rowVisible && visibleColumns[col] ? "" : "none";
      }
    });

    for (let col = 0; col < tripColumnCount; col += 1) {
      const headerCell = headerCells[col + 1];
      if (!headerCell) {
        continue;
      }
      headerCell.style.display = visibleColumns[col] ? "" : "none";
    }

    updateDownloadLink(startIndexRaw, endIndexRaw, startMinutes, endMinutes, isFilteringActive);
  }

  function updateDownloadLink(startIndex, endIndex, startMinutes, endMinutes, isFilteringActive) {
    if (!downloadLink || !baseDownloadHref) {
      return;
    }

    const url = new URL(baseDownloadHref, window.location.origin);
    if (isFilteringActive) {
      if (startIndex !== null) {
        url.searchParams.set("start_index", String(startIndex));
      } else {
        url.searchParams.delete("start_index");
      }

      if (endIndex !== null) {
        url.searchParams.set("end_index", String(endIndex));
      } else {
        url.searchParams.delete("end_index");
      }

      url.searchParams.set("start_time", formatMinutes(startMinutes));
      url.searchParams.set("end_time", formatMinutes(endMinutes));

      if (omitIntermediateStopsCheckbox.checked) {
        url.searchParams.set("omit_intermediate", "1");
      } else {
        url.searchParams.delete("omit_intermediate");
      }
    } else {
      url.searchParams.delete("start_index");
      url.searchParams.delete("end_index");
      url.searchParams.delete("start_time");
      url.searchParams.delete("end_time");
      url.searchParams.delete("omit_intermediate");
    }

    const search = url.searchParams.toString();
    downloadLink.href = search ? `${url.pathname}?${search}` : url.pathname;
  }

  function applyColumnOrder(columnOrder) {
    if (headerCells[0] && headerCells[0].parentElement) {
      columnOrder.forEach((colIndex) => {
        const headerCell = headerCells[colIndex + 1];
        if (headerCell) {
          headerCells[0].parentElement.appendChild(headerCell);
        }
      });
    }

    rowModels.forEach((row) => {
      columnOrder.forEach((colIndex) => {
        const bodyCell = row.cells[colIndex + 1];
        if (bodyCell) {
          row.rowEl.appendChild(bodyCell);
        }
      });
    });
  }

  function pickTripTime(colIndex, rowStart, rowEnd, pickEarliest) {
    if (pickEarliest) {
      for (let row = rowStart; row <= rowEnd; row += 1) {
        const minuteValue = rowModels[row].times[colIndex];
        if (minuteValue !== null) {
          return minuteValue;
        }
      }
      return null;
    }

    for (let row = rowEnd; row >= rowStart; row -= 1) {
      const minuteValue = rowModels[row].times[colIndex];
      if (minuteValue !== null) {
        return minuteValue;
      }
    }
    return null;
  }
});

function parseTableTime(timeText) {
  if (!timeText) {
    return null;
  }

  const normalized = timeText.trim();
  if (normalized === "\u2193" || normalized === "N/A") {
    return null;
  }

  const match = normalized.match(/^(\d{1,2}):(\d{2})$/);
  if (!match) {
    return null;
  }

  const hours = Number.parseInt(match[1], 10);
  const minutes = Number.parseInt(match[2], 10);
  if (Number.isNaN(hours) || Number.isNaN(minutes) || minutes > 59) {
    return null;
  }

  return (hours * 60) + minutes;
}

function renderStopOptions(selectEl, options, selectedIndex, defaultLabel, includeOption) {
  const selectedValue = selectedIndex === null ? "" : String(selectedIndex);
  selectEl.replaceChildren();
  const allOption = document.createElement("option");
  allOption.value = "";
  allOption.textContent = defaultLabel;
  selectEl.appendChild(allOption);

  options.forEach((optionData) => {
    if (!includeOption(optionData.index)) {
      return;
    }
    const option = document.createElement("option");
    option.value = String(optionData.index);
    option.textContent = optionData.name;
    selectEl.appendChild(option);
  });

  const hasSelection = selectedIndex !== null
    && includeOption(selectedIndex)
    && options.some((optionData) => optionData.index === selectedIndex);
  selectEl.value = hasSelection ? selectedValue : "";
}

function parseOptionIndex(value, maxExclusive) {
  if (value === "") {
    return null;
  }
  const parsed = Number.parseInt(value, 10);
  if (Number.isNaN(parsed) || parsed < 0) {
    return null;
  }
  if (Number.isInteger(maxExclusive) && parsed >= maxExclusive) {
    return null;
  }
  return parsed;
}

function normalizeTripTimes(departure, arrival) {
  let arr = arrival;

  while (arr < departure) {
    arr += 24 * 60;
  }

  return { departure, arrival: arr };
}

function setInputBounds(input, min, max) {
  input.min = String(min);
  input.max = String(max);
}

function sanitizeNumericInput(input) {
  const min = Number.parseInt(input.min, 10);
  const max = Number.parseInt(input.max, 10);
  const fallback = Number.isNaN(min) ? 0 : min;

  let parsed = Number.parseInt(input.value, 10);
  if (Number.isNaN(parsed)) {
    parsed = fallback;
  }

  if (!Number.isNaN(min) && parsed < min) {
    parsed = min;
  }
  if (!Number.isNaN(max) && parsed > max) {
    parsed = max;
  }

  input.value = String(parsed).padStart(2, "0");
  return parsed;
}

function toTotalMinutes(hours, minutes) {
  return (hours * 60) + minutes;
}

function formatMinutes(totalMinutes) {
  const safeValue = Math.max(0, totalMinutes);
  const hours = Math.floor(safeValue / 60);
  const minutes = safeValue % 60;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
}

function setTimeInputs(hourInput, minuteInput, totalMinutes) {
  const safeValue = Math.max(0, totalMinutes);
  const hours = Math.floor(safeValue / 60);
  const minutes = safeValue % 60;
  hourInput.value = String(hours).padStart(2, "0");
  minuteInput.value = String(minutes).padStart(2, "0");
}
