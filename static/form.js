function resetDirectionOptions() {
    const directionSelect = document.getElementById("direction");
    directionSelect.innerHTML = [
        '<option value="">-- Select a direction --</option>',
        '<option value="0">Direction 0</option>',
        '<option value="1">Direction 1</option>'
    ].join("");
}

function updateRoutes(routesByAgency) {
    const agency = document.getElementById("agency").value;
    const routeSelect = document.getElementById("route");

    routeSelect.innerHTML = '<option value="">-- Select a route --</option>';

    if (agency && routesByAgency[agency]) {
        const agencyRoutes = routesByAgency[agency];
        const shortNames = agencyRoutes.map(route => String(route.route_short_name ?? route.route_short_names ?? "").trim());
        const allShortNamesPresent = shortNames.every(shortName => shortName.length > 0);
        const shortNamesAreUnique = new Set(shortNames).size === shortNames.length;
        const useShortName = allShortNamesPresent && shortNamesAreUnique;

        agencyRoutes.forEach(route => {
            const labelId = useShortName
                ? route.route_short_name
                : route.route_id;
            const option = document.createElement("option");
            option.value = route.route_id;
            option.textContent = `${labelId} - ${route.route_long_name}`;
            routeSelect.appendChild(option);
        });
    }

    resetDirectionOptions();
}

async function updateDirectionOptions() {
    const agency = document.getElementById("agency").value;
    const route = document.getElementById("route").value;
    const directionSelect = document.getElementById("direction");

    if (!agency || !route) {
        resetDirectionOptions();
        return;
    }

    try {
        const response = await fetch(`/direction-options?agency=${encodeURIComponent(agency)}&route=${encodeURIComponent(route)}`);
        const data = await response.json();

        directionSelect.innerHTML = '<option value="">-- Select a direction --</option>';

        data.options.forEach(optionData => {
            const option = document.createElement("option");
            option.value = optionData.value;
            option.textContent = optionData.label;
            directionSelect.appendChild(option);
        });
    } catch (_error) {
        resetDirectionOptions();
    }
}

document.addEventListener("DOMContentLoaded", function () {
    const agencySelect = document.getElementById("agency");
    const routeSelect = document.getElementById("route");
    const routesByAgency = JSON.parse(agencySelect.dataset.routes);

    agencySelect.addEventListener("change", function () {
        updateRoutes(routesByAgency);
    });

    routeSelect.addEventListener("change", function () {
        updateDirectionOptions();
    });
});
