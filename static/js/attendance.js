// Volunteer attendance page.
//
// Two things happen here:
//  1. If a map container is present, draw the event's geofence circle so
//     the volunteer can see it.
//  2. Wire up the "Mark attendance" button: capture GPS via the browser's
//     Geolocation API, show an instant client-side distance estimate (pure
//     UX — it does NOT decide accept/reject), then submit the coordinates
//     to the server, which makes the real decision and re-renders the page.

function haversineMeters(lat1, lon1, lat2, lon2) {
  var R = 6371000;
  var toRad = function (d) { return (d * Math.PI) / 180; };
  var dLat = toRad(lat2 - lat1);
  var dLon = toRad(lon2 - lon1);
  var a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(a)));
}

document.addEventListener('DOMContentLoaded', function () {
  var btn = document.getElementById('mark-attendance-btn');
  if (!btn) return;

  var eventLat = parseFloat(btn.dataset.eventLat);
  var eventLng = parseFloat(btn.dataset.eventLng);
  var radius = parseFloat(btn.dataset.radius);
  var hasCoords = !isNaN(eventLat) && !isNaN(eventLng);

  var statusEl = document.getElementById('location-status');
  var form = document.getElementById('attendance-form');
  var latField = document.getElementById('latitude');
  var lngField = document.getElementById('longitude');
  var accField = document.getElementById('accuracy');

  // --- Geofence map (read-only) ---------------------------------------------
  var mapEl = document.getElementById('geofence-map');
  var volunteerMarker = null;
  var map = null;

  if (mapEl && hasCoords && window.L) {
    map = L.map('geofence-map').setView([eventLat, eventLng], 16);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map);
    L.circle([eventLat, eventLng], {
      radius: radius, color: '#D97706', fillColor: '#D97706', fillOpacity: 0.12, weight: 2,
    }).addTo(map).bindPopup('Event geofence (' + radius + 'm radius)');
  }

  function showVolunteerOnMap(lat, lng) {
    if (!map) return;
    if (volunteerMarker) {
      volunteerMarker.setLatLng([lat, lng]);
    } else {
      volunteerMarker = L.circleMarker([lat, lng], {
        radius: 8, color: '#14171C', fillColor: '#3C6E9E', fillOpacity: 0.9, weight: 2,
      }).addTo(map).bindPopup('Your location');
    }
    map.fitBounds(L.latLngBounds([[eventLat, eventLng], [lat, lng]]).pad(0.4));
  }

  // --- Mark attendance button -------------------------------------------------
  function setStatus(msg, kind) {
    if (!statusEl) return;
    statusEl.textContent = msg;
    statusEl.className = 'text-sm mt-3 font-medium ' +
      (kind === 'error' ? 'text-rose-600' : kind === 'success' ? 'text-emerald-600' : 'text-ink/50');
  }

  btn.addEventListener('click', function () {
    if (!navigator.geolocation) {
      setStatus("Geolocation isn't supported by this browser.", 'error');
      return;
    }
    btn.disabled = true;
    setStatus('Getting your location\u2026', 'muted');

    navigator.geolocation.getCurrentPosition(
      function (position) {
        var lat = position.coords.latitude;
        var lng = position.coords.longitude;

        if (latField) latField.value = lat;
        if (lngField) lngField.value = lng;
        if (accField) accField.value = position.coords.accuracy;

        showVolunteerOnMap(lat, lng);

        if (hasCoords) {
          var distance = Math.round(haversineMeters(lat, lng, eventLat, eventLng));
          if (distance <= radius) {
            setStatus('You\u2019re about ' + distance + 'm from the venue \u2014 within range. Submitting\u2026', 'success');
          } else {
            setStatus('You\u2019re about ' + distance + 'm from the venue \u2014 outside the ' + radius + 'm geofence. Submitting for the record\u2026', 'error');
          }
        } else {
          setStatus('Location captured. Submitting\u2026', 'muted');
        }

        if (form) form.submit();
      },
      function (error) {
        btn.disabled = false;
        var msg = 'Unable to retrieve your location.';
        if (error.code === error.PERMISSION_DENIED) msg = 'Location permission denied. Please allow location access for this site and try again.';
        else if (error.code === error.POSITION_UNAVAILABLE) msg = 'Location information is unavailable right now. Try again in a moment.';
        else if (error.code === error.TIMEOUT) msg = 'Location request timed out. Try again.';
        setStatus(msg, 'error');
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }
    );
  });
});
