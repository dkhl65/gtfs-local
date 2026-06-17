function updateRoutes(routesByAgency) {
    const agency = document.getElementById("agency").value;
    const routeSelect = document.getElementById("route");

    routeSelect.innerHTML = '<option value="">-- Select a route --</option>';

    if (agency && routesByAgency[agency]) {
        routesByAgency[agency].forEach(route => {
            const option = document.createElement("option");
            option.value = route.route_id;
            option.textContent = `Route ${route.route_short_name}`;
            routeSelect.appendChild(option);
        });
    }
}

document.addEventListener("DOMContentLoaded", function () {
    const agencySelect = document.getElementById("agency");
    const routesByAgency = JSON.parse(agencySelect.dataset.routes);

    agencySelect.addEventListener("change", function () {
        updateRoutes(routesByAgency);
    });
});
