document.addEventListener("DOMContentLoaded", function () {

    // ==========================
    // REGION DATA
    // ==========================

    const regions = {

        Chamoli: {
            rainfall: 82,
            water: 3.8,
            soil: 78,
            temp: 18,
            risk: 87,
            level: "HIGH",
            prediction: "Flash flood likely",
            time: "2–4 Hours"
        },

        Kedarnath: {
            rainfall: 65,
            water: 2.9,
            soil: 71,
            temp: 15,
            risk: 64,
            level: "MODERATE",
            prediction: "Continuous monitoring required",
            time: "4–6 Hours"
        },

        Manali: {
            rainfall: 45,
            water: 2.1,
            soil: 58,
            temp: 16,
            risk: 38,
            level: "LOW",
            prediction: "No immediate flood threat",
            time: "Low Risk"
        },

        Sikkim: {
            rainfall: 105,
            water: 4.2,
            soil: 86,
            temp: 17,
            risk: 78,
            level: "HIGH",
            prediction: "Flash flood possibility",
            time: "2–3 Hours"
        }

    };


    // ==========================
    // PAGE NAVIGATION
    // ==========================

    const navLinks =
        document.querySelectorAll("nav a");

    const pages =
        document.querySelectorAll(".page");


    navLinks.forEach(function (link) {

        link.addEventListener("click", function (e) {

            e.preventDefault();

            const pageName =
                this.getAttribute("data-page");


            // Hide all pages

            pages.forEach(function (page) {

                page.classList.remove(
                    "active-page"
                );

            });


            // Show selected page

            const selectedPage =
                document.getElementById(pageName);


            if (selectedPage) {

                selectedPage.classList.add(
                    "active-page"
                );

            }


            // Active navigation

            navLinks.forEach(function (item) {

                item.classList.remove("active");

            });

            this.classList.add("active");


            // Scroll to top

            window.scrollTo({
                top: 0,
                behavior: "smooth"
            });

        });

    });



    // ==========================
    // REGION SELECT
    // ==========================

    const regionSelect =
        document.getElementById(
            "regionSelect"
        );


    function updateRegion(regionName) {

        const current =
            regions[regionName];

        if (!current) return;


        document.getElementById(
            "rainfall"
        ).innerHTML =
            current.rainfall +
            " <small>mm/hr</small>";


        document.getElementById(
            "waterLevel"
        ).innerHTML =
            current.water +
            " <small>m</small>";


        document.getElementById(
            "soilMoisture"
        ).innerHTML =
            current.soil +
            " <small>%</small>";


        document.getElementById(
            "temperature"
        ).innerHTML =
            current.temp +
            " <small>°C</small>";


        document.getElementById(
            "riskScore"
        ).innerHTML =
            current.risk +
            "<small>%</small>";


        document.getElementById(
            "riskProgress"
        ).style.width =
            current.risk + "%";


        let icon = "🟢";

        if (current.level === "MODERATE") {
            icon = "🟡";
        }

        if (current.level === "HIGH") {
            icon = "🟠";
        }

        if (current.level === "CRITICAL") {
            icon = "🔴";
        }


        document.getElementById(
            "riskLevel"
        ).textContent =
            icon +
            " " +
            current.level +
            " RISK";
            document.getElementById(
            "prediction"
        ).textContent =
            current.prediction;


        const details =
            document.querySelectorAll(
                ".region-details strong"
            );


        if (details.length >= 5) {

            details[0].textContent =
                current.rainfall + " mm/hr";

            details[1].textContent =
                current.water + " m";

            details[2].textContent =
                current.soil + "%";

            details[3].textContent =
                current.risk >= 70
                    ? "38°"
                    : "30°";

            details[4].textContent =
                current.time;

        }

    }


    regionSelect.addEventListener(
        "change",
        function () {

            updateRegion(
                this.value
            );

        }
    );



    // ==========================
    // NOTIFICATION
    // ==========================

    const notification =
        document.querySelector(
            ".notification"
        );


    notification.addEventListener(
        "click",
        function () {

            // Open Alerts

            pages.forEach(function (page) {

                page.classList.remove(
                    "active-page"
                );

            });


            document.getElementById(
                "alerts"
            ).classList.add(
                "active-page"
            );


            navLinks.forEach(function (item) {

                item.classList.remove(
                    "active"
                );

            });


            document
                .querySelector(
                    '[data-page="alerts"]'
                )
                .classList.add(
                    "active"
                );

        }
    );



    // ==========================
    // MAP MARKERS
    // ==========================

    const markers =
        document.querySelectorAll(
            ".risk-marker"
        );


    markers.forEach(function (marker) {

        marker.addEventListener(
            "click",
            function () {

                const region =
                    this.getAttribute(
                        "data-region"
                    );


                if (regionSelect) {

                    regionSelect.value =
                        region;

                }


                updateRegion(region);


                // Open map page

                pages.forEach(function (page) {

                    page.classList.remove(
                        "active-page"
                    );

                });


                document.getElementById(
                    "map"
                ).classList.add(
                    "active-page"
                );


                navLinks.forEach(function (item) {

                    item.classList.remove(
                        "active"
                    );

                });


                document
                    .querySelector(
                        '[data-page="map"]'
                    )
                    .classList.add(
                        "active"
                    );

            }
        );

    });



    // ==========================
    // INITIAL DATA
    // ==========================

    updateRegion("Chamoli");


    console.log(
        "FlashGuard frontend loaded successfully."
    );

});