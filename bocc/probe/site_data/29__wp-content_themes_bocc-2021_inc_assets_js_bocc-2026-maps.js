jQuery(document).ready(function() {
  
    /* Utilities */

    // Function to put the CSV into a geojson format
    function mp_build_data(items) {
        var mp_geojson = [];
        jQuery.each( items, function( index, value ){ 

            mp_geojson.push( {
                "type": "Feature",
                "properties": {
                    "name" : value["Title"],
                    "country" : value["Country"],
                    "popupContent": value["Details"],
                    "icon": greyIcon,
                    "id" : "m"+ index,
                    "img" : value["Image_url"],
                    "readMore": value["Case_study_url"],
                    "sector": value["Sector"]
                    },
                    "geometry": {
                        "type": "Point",
                        "coordinates": [value["Longitude"],value["Latitude"]]
                    }
            });
                 
        })
       // console.log(mp_geojson);
        return mp_geojson;
    }
    // Create some icons etc for our features
    var redIcon = new L.Icon({
        iconUrl: '/wp-content/themes/bocc-2021/inc/assets/images/bocc2025/BOCC-2024-map-marker.png',
        iconSize: [37, 46],
        iconAnchor: [12, 41],
        popupAnchor: [1, -34],
        shadowSize: [41, 41]
    });
    var greyIcon = new L.Icon({
        iconUrl: '/wp-content/themes/bocc-2021/inc/assets/images/bocc2025/BOCC-2024-map-marker.png',
        iconSize: [37, 46],
        iconAnchor: [12, 41],
        popupAnchor: [1, -34],
        shadowSize: [41, 41]
    });
    // Build some functions for the geoJSON 
    function onEachFeature(feature, layer) {
        layer.on('click', function(e) {
            jQuery('.leaflet-marker-icon').attr('src', '/wp-content/themes/bocc-2021/inc/assets/images/bocc2025/BOCC-2024-map-marker.png');
            if(feature.properties.img != '') {
                var img = '<img src="'+feature.properties.img+'" alt="'+feature.properties.name+'" /><div class="clear"></div>';
            }  else {
                var img = '';
            }
            if(feature.properties.readMore != '') {
                jQuery('.map-case').html(
                    '<div class="map-case-link"><span><a href="'+feature.properties.readMore+'">Read this story in-depth</a></span></div>'
                    );
            } else {
                jQuery('.map-case').html('');
            }

            var popup = feature.properties.popupContent.replace(/(?:\r\n|\r|\n)/g, '<br>');
            popup = popup.replace(/Key companies:/g, '<strong>Key Companies:</strong>');
            popup = popup.replace(/Key banks:/g, '<strong>Key Banks:</strong>');
            popup = popup.replace(/Status:/g, '<strong>Status:</strong>');
            //var sector = '<div class="sectors '+feature.properties.sector+'"</div>';
            if (feature.properties.sector != '') {
                var sectorText = sectorNames(feature.properties.sector);
                jQuery('.map-info').html(
                    '<h4>'+feature.properties.name+'</h4>'+img+'<h5>'+feature.properties.country+'</h5>'+popup+' <div class="sector-wrap"><div class="sectors '+feature.properties.sector+'"></div><span>'+sectorText+'</span></div>'
                    );
            } else {
                jQuery('.map-info').html(
                    '<h4>'+feature.properties.name+'</h4>'+img+''+popup
                    );
            }

            //map.setView([(e.latlng.lat) , e.latlng.lng]);
            layer.setIcon(redIcon);
        }); 
    }

    function sectorNames(sector) {
        if (sector == 'lng') {
            return "Methane";
        }
        if (sector == 'expansion') {
            return "Expansion";
        }
        if (sector == 'tar_sands') {
            return "Tar Sands Oil";
        }
        if (sector == 'arctic') {
            return "Arctic Oil & Gas";
        }
        if (sector == 'amazon') {
            return "Amazon Oil & Gas";
        }
        if (sector == 'offshore') {
            return "Ultra-Deepwater Oil & Gas";
        }
        if (sector == 'fracked') {
            return "Fracked Oil & Gas";
        }
        if (sector == 'coal_mining') {
            return "Thermal Coal Mining";
        }
        if (sector == 'coal_power') {
            return "Coal Power";
        }
        if (sector == 'gas_fired') {
            return "Gas Power";
        }
        if (sector == 'met_coal') {
            return "Metallurgical Coal Mining";
        }
    }
    /* Make the Map */

    if (jQuery(window).width() > 870) {
        var map = L.map('map', { 
            minZoom: 2, 
            maxZoom: 12, 
            zoomControl: false
        }).setView([23.795052611005723, 123.01388960469104], 2);
	} else {
        var map = L.map('map', { 
            minZoom: 1, 
            maxZoom: 9, 
            zoomControl: false
        }).setView([16.289982220309298, -8.440111993560397], 1);
    }
    // Add basemap
  var CartoDB_VoyagerLabelsUnder = L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager_labels_under/{z}/{x}/{y}{r}.png?key=cb1_2tlj_1_27d82762709574fdd2700e41', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
        maxZoom: 20,

    });
   CartoDB_VoyagerLabelsUnder.addTo(map); 

    L.control.attribution({
        position: 'bottomleft'
    }).addTo(map);

    // Initiate clusters
    var markersCluster = L.markerClusterGroup({maxClusterRadius: 30});

    // Build the geojson from the csv
    var items = '';
    var mp_final_geojson = '';
    // TODO: Update this to the latest version after it is provided
    var mp_filename = '/wp-content/themes/bocc-2021/inc/bcc-data-2025/BOCC-2025-stories.csv';
    jQuery.get( mp_filename, function(data) {
        items = jQuery.csv.toObjects(data);
        mp_final_geojson =  mp_build_data(items);
        //console.log(mp_final_geojson);
        var geoData = L.geoJSON(mp_final_geojson, {
            pointToLayer: function (feature, latlng) {
                    
                    return L.marker(latlng, {icon: greyIcon, alt: feature.properties.id});
            },
            onEachFeature: onEachFeature
        })
        // Add all the markers to the cluster then to the map
        markersCluster.addLayer(geoData);
        markersCluster.addTo(map);
    }).done(function(){
        // Pick the item we show by default (using this awkward way since leaflet weirdly doesn't assign ids)
        jQuery('img[alt="m14"]').click();
    })
    
    // Move the zoom control
    L.control.zoom({
        position: 'bottomleft'
    }).addTo(map);



});