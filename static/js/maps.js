// Editable Leaflet map for the admin "create/edit event" form.
// Lets the admin click the map (or drag the marker, or use their own GPS)
// to set the event's venue location, and shows the geofence radius live
// as a circle that resizes as the radius input changes.

function initEventLocationMap(containerId, latInputId, lngInputId, radiusInputId, initialLat, initialLng, initialRadius) {
  var latInput = document.getElementById(latInputId);
  var lngInput = document.getElementById(lngInputId);
  var radiusInput = document.getElementById(radiusInputId);

  var hasInitial = !isNaN(initialLat) && !isNaN(initialLng);
  var startLat = hasInitial ? initialLat : 19.0760;
  var startLng = hasInitial ? initialLng : 72.8777;
  var startRadius = (!isNaN(initialRadius) && initialRadius > 0) ? initialRadius : 100;

  var map = L.map(containerId).setView([startLat, startLng], hasInitial ? 16 : 11);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
  }).addTo(map);

  var marker = L.marker([startLat, startLng], { draggable: true }).addTo(map);
  var circle = L.circle([startLat, startLng], {
    radius: startRadius, color: '#D97706', fillColor: '#D97706', fillOpacity: 0.12, weight: 2,
  }).addTo(map);

  function setPoint(lat, lng, recenter) {
    marker.setLatLng([lat, lng]);
    circle.setLatLng([lat, lng]);
    if (latInput) latInput.value = lat.toFixed(6);
    if (lngInput) lngInput.value = lng.toFixed(6);
    if (recenter) map.setView([lat, lng], Math.max(map.getZoom(), 15));
  }

  map.on('click', function (e) { setPoint(e.latlng.lat, e.latlng.lng, false); });
  marker.on('dragend', function () {
    var pos = marker.getLatLng();
    setPoint(pos.lat, pos.lng, false);
  });

  function syncFromInputs() {
    var lat = parseFloat(latInput.value);
    var lng = parseFloat(lngInput.value);
    if (!isNaN(lat) && !isNaN(lng)) setPoint(lat, lng, true);
  }
  if (latInput) latInput.addEventListener('change', syncFromInputs);
  if (lngInput) lngInput.addEventListener('change', syncFromInputs);

  if (radiusInput) {
    radiusInput.addEventListener('input', function () {
      var r = parseFloat(radiusInput.value);
      if (!isNaN(r) && r > 0) circle.setRadius(r);
    });
  }

  var gpsBtn = document.getElementById('use-my-location-btn');
  if (gpsBtn) {
    gpsBtn.addEventListener('click', function () {
      if (!navigator.geolocation) {
        alert("Geolocation isn't supported by this browser.");
        return;
      }
      var original = gpsBtn.textContent;
      gpsBtn.disabled = true;
      gpsBtn.textContent = 'Locating\u2026';
      navigator.geolocation.getCurrentPosition(
        function (position) {
          setPoint(position.coords.latitude, position.coords.longitude, true);
          gpsBtn.disabled = false;
          gpsBtn.textContent = original;
        },
        function () {
          alert('Could not get your current location. Click the map instead to set the venue.');
          gpsBtn.disabled = false;
          gpsBtn.textContent = original;
        },
        { enableHighAccuracy: true, timeout: 15000 }
      );
    });
  }

  return map;
}
