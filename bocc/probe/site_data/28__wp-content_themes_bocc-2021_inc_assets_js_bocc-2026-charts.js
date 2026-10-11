// Big ass Highcharts theme that we can call later to keep things tidy 

var fontColor = '#000000';
Highcharts.theme = {
	colors: ['#f57e20','#007c9d','#d2232a','#ebac20', 
		'#24448e','#6a9913','#c444c4', '#55BF3B', '#7798BF', '#aaeeee'],
	/* colors: ['#b3ddcc','#8acdce','#46aace', '#3d91be', '#2d5e9e', '#24448e', 
	        '#eeaaee', '#55BF3B', '#DF5353', '#7798BF', '#aaeeee'],*/
	chart: {
		backgroundColor: {
			linearGradient: { x1: 0, y1: 0, x2: 1, y2: 1 },
			stops: [
				[0, '#cdcdcd'],
				[1, '#cdcdcd']
			]
		},
		style: {
			fontFamily: 'interstate-mono',
			fontSize: '14px'
		},
		plotBorderColor: fontColor
	},
	title: {
		style: {
			color: fontColor,
			textTransform: 'uppercase',
			fontSize: '20px'
		}
	},
	subtitle: {
		style: {
			color: fontColor,
			textTransform: 'uppercase'
		}
	},
	xAxis: {
		gridLineColor: fontColor,
		labels: {
			style: {
				color: fontColor,
				fontSize: '14px'
			}
		},
		lineColor: fontColor,
		minorGridLineColor: '#505053',
		tickColor: fontColor,
		title: {
			style: {
				color: fontColor
			},
						
		}
	},
	yAxis: {
		gridLineColor: '#aaaaaa',
		labels: {
			style: {
				color: fontColor
			}
		},
		lineColor: '#aaaaaa',
		minorGridLineColor: '#505053',
		tickColor: '#707073',
		tickWidth: 0,
		title: {
			style: {
				color: fontColor
			}
		}
	},
	tooltip: {
		backgroundColor: 'rgba(0, 0, 0, 0.85)',
		style: {
			color: '#F0F0F0'
		}
	},
	plotOptions: {
		series: {
			dataLabels: {
				color: fontColor,
				style: {
					fontSize: '14px'
				}
			},
			marker: {
				lineColor: fontColor
			}
		},
		boxplot: {
			fillColor: '#505053'
		},
		candlestick: {
			lineColor: fontColor
		},
		errorbar: {
			color: fontColor
		},
		bar: {
			borderColor: '#000000'
		},
		column: {
			borderColor: null
		}
		
	},
	legend: {
		backgroundColor: '#cdcdcd',
		itemStyle: {
			color: fontColor
		},
		itemHoverStyle: {
			color: fontColor
		},
		itemHiddenStyle: {
			color: '#cdcdcd'
		},
		title: {
			style: {
				color: '#aaaaaa'
			}
		}, 
		reversed: true,
		verticalAlign: 'top',
		align: 'left',
	},
	credits: {
		style: {
			color: '#999999'
		}
	},
	labels: {
		style: {
			color: fontColor
		}
	},
	drilldown: {
		activeAxisLabelStyle: {
			color: fontColor
		},
		activeDataLabelStyle: {
			color: fontColor
		}
	},
	navigation: {
		buttonOptions: {
			symbolStroke: '#DDDDDD',
			theme: {
				fill: '#505053'
			}
		}
	},
	// scroll charts
	rangeSelector: {
		buttonTheme: {
			fill: '#505053',
			stroke: '#000000',
			style: {
				color: '#CCC'
			},
			states: {
				hover: {
					fill: '#707073',
					stroke: '#000000',
					style: {
						color: 'white'
					}
				},
				select: {
					fill: '#000003',
					stroke: '#000000',
					style: {
						color: 'white'
					}
				}
			}
		},
		inputBoxBorderColor: '#505053',
		inputStyle: {
			backgroundColor: '#333',
			color: 'silver'
		},
		labelStyle: {
			color: 'silver'
		}
	},
	navigator: {
		handles: {
			backgroundColor: '#666',
			borderColor: '#AAA'
		},
		outlineColor: '#CCC',
		maskFill: 'rgba(255,255,255,0.1)',
		series: {
			color: '#7798BF',
			lineColor: '#A6C7ED'
		},
		xAxis: {
			gridLineColor: '#505053'
		}
	},
	scrollbar: {
		barBackgroundColor: '#808083',
		barBorderColor: '#808083',
		buttonArrowColor: '#CCC',
		buttonBackgroundColor: '#606063',
		buttonBorderColor: '#606063',
		rifleColor: '#FFF',
		trackBackgroundColor: '#404043',
		trackBorderColor: '#404043'
	}
};


/* Fossil Fuel Funding Chart */

function fc_build_categories(items) {
	// collect the names of all the banks into an array for use on the y-axis labels	
	var banks = [];
	jQuery.each( items, function( index, value )
    { 
	    banks.push(value["Bank"]);
    });
    return banks;
}	

function fc_build_data(items) {
	// Builds the yearly values from the CSV into JSON 
    var years = {};

	var year_2021 = [];
	var year_2022 = [];
    var year_2023 = [];
	var year_2024 = [];
    var year_2025 = [];

    jQuery.each( items, function( index, value )
    { 

		year_2021.push(parseInt(value["2021"]));
		year_2022.push(parseInt(value["2022"]));
		year_2023.push(parseInt(value["2023"]));
		year_2024.push(parseInt(value["2024"]));
        year_2025.push(parseInt(value["2025"]));
    });
    
	var years = [{ 
		name: '2025',
		data: year_2025,
   },{ 
		name: '2024',
		data: year_2024,
   },{ 
		name: '2023',
		data: year_2023,
   },{ 
		name: '2022',
		data: year_2022,
   },{ 
		name: '2021',
		data: year_2021,
   }]

    return years;		
}

function fc_declare_chart(chart_data,chart_categories) {
	// The function that builds the Highchart chart
	// Apply the theme
	Highcharts.setOptions(Highcharts.theme);

	// builds the highcharts fossil fuel financing chart 
    Highcharts.setOptions({
		lang: {
			thousandsSep: ',',
			numericSymbols:  [ "k" , "M" , "B" , "T" , "P" , "E"]
		}

	});
   Highcharts.chart('data-container', {
	    chart: {
	        type: 'bar',
	    },
	    title: {
	        text: 'Investment in Fossil Fuels'
	    },
		/* tooltip: {
			formatter: function() {
			  return  this.x + '<br /><b>'+ this.series.name +': '+ Highcharts.numberFormat((this.y/1000000000) , 2, '.',',') + ' B USD </b><br/>';
			}
		},*/
	    xAxis: {
	        categories: chart_categories,
	    },
	    yAxis: {
	        min: 0,
	        title: {
	            text: 'Financing in US Dollars (B = Billions)',
	           margin: 40,
	        }, 
	        labels: {
				formatter: function () {
					  return '$' +  this.value / 1000000000 + 'B';
                }
            },
            stackLabels: {
			    enabled: true,
			    style: {
			        fontWeight: 'normal',
			        color: fontColor,
			        fontSize: '13px',
			        textOutline: null,
			    },
			    formatter: function () {
					  return '$' +  (this.total  / 1000000000).toFixed(2) + ' B';
                }
			 },
			 opposite: true,	 
	    },
	    plotOptions: {
	        series: {
	            stacking: 'normal',
				pointWidth: 20
	        },
	    },
	    series: chart_data
   	});
}

function fc_declare_single_chart(chart_data,chart_categories) {
	// builds the individual company bar chart for the profiles section

	// Apply the theme
	Highcharts.setOptions(Highcharts.theme);



   Highcharts.chart('single-total-container', Highcharts.merge({
	    chart: {
	        type: 'bar',
	    },
	    title: {
	        text: 'Investment in Fossil Fuels'
	    },
		/* tooltip: {
			formatter: function() {
			  return  this.x + '<br /><b>'+ this.series.name +': '+ Highcharts.numberFormat((this.y/1000000000) , 2, '.',',') + ' B USD </b><br/>';
			}
		},*/
	    xAxis: {
	        categories: chart_categories,
	    },
	    yAxis: {
	        min: 0,
	        title: {
	            text: 'Bank Financing in US Dollars (B = Billions)',
	           margin: 40,
	        }, 
	        labels: {
				formatter: function () {
					  return '$' +  this.value / 1000000000 + 'B';
                }
            },
            stackLabels: {
			    enabled: true,
			    style: {
			        fontWeight: 'normal',
			        color: fontColor,
			        fontSize: '13px',
			        textOutline: null,
			    },
			    formatter: function () {
					  return '$' +  (this.total  / 1000000000).toFixed(2) + ' B';
                }
			 },
			 opposite: true,	 
	    },
	    plotOptions: {
	        series: {
	            stacking: 'normal',
				pointWidth: 20
	        },
	    },
	    series: chart_data
   	}, 
		{
			lang: {
				thousandsSep: ',',
				numericSymbols:  [ "k" , "M" , "B" , "T" , "P" , "E"]
			},
			legend: {
				enabled: true,
				backgroundColor: '#ffffff',
				align: 'center',
				verticalAlign: 'bottom',
			},
			chart: {
				backgroundColor: '#ffffff',
				height: '190px',
			},
			xAxis: {
	
				labels: {
					enabled: false
				}
			},

	})
   );
}

function fc_get_data(series_name, callback) {
	// get our data file based on the select and run the build only after it returns
	return jQuery.get( series_name, {}, callback);
}

function fc_build_series(data) {
	// take the data from the file and convert it to an object and then build the data series and category arrays for the chart
	var items = jQuery.csv.toObjects(data);
	// order the banks by their total financing, descending, so the chart shows the largest financiers first
	items.sort(function (a, b) {
		return parseInt(b["Total"]) - parseInt(a["Total"]);
	});
	var data = fc_build_data(items);
	var categories = fc_build_categories(items);
	fc_declare_chart(data, categories);
}


/* Full Data Table */

// finds the unique names of banks and companies in the csv data	
function getUnique(inputArray) 
{
	var outputArray = [];
	for (var i = 0; i < inputArray.length; i++)
	{
		if ((jQuery.inArray(inputArray[i], outputArray)) == -1)
		{
			outputArray.push(inputArray[i]);
		}
	}
	return outputArray;
}

// creates our standard number format across the amounts
function numberFormat(data) {
	if(data > 0) { 
	        var formatted = numeral(data).divide(1000000).format('0,0.00'); 
	        formatted = (formatted + ''); 
	    } else {
		    var formatted = '0';
	    }
	    
	return formatted;
}
// creates our standard number format across the amounts
function numberFormatCSV(data) {
	if(data > 0) { 
	        var formatted = numeral(data).divide(1000000).format('00.00'); 
	        formatted = (formatted + ''); 
	    } else {
		    var formatted = '0';
	    }
	    
	return formatted;
}
// buildes the data into a table based on the select inputs
function buildData(bank, company, parent, items)
{
	items = items.sort(function(a, b){
	    return b.Total-a.Total
	}); 
    jQuery("#output").empty();
 
	var total = 0;
	var uniqeClients = [];
	var output = '';
    jQuery.each( items, function( index, data )
    {	
		var year2025 = numberFormat(data["2025"]);
		var year2024 = numberFormat(data["2024"]);
		var year2023 = numberFormat(data["2023"]);
		var year2022 = numberFormat(data["2022"]);
		var year2021 = numberFormat(data["2021"]);
	    
	    var grandTotal = numberFormat(data["Total"]);
	    
	    if ((company == 'all') & (parent == 'all')) {
			
		    if (bank == data.Bank) {
			     output += '<tr><td class="name">' + data.Company + '<span class="flag-icon flag-icon-' + data.Company_Country_Code.toLowerCase() + '"></span></td><td class="number"> ' + year2021 + '</td><td class="number"> ' + year2022 + '</td><td class="number"> ' + year2023 + '</td><td class="number"> ' + year2024 + '</td><td class="number"> ' + year2025 + '</td><td class="number"> ' + grandTotal + '</td></tr>';
			     total = (total+parseInt(data["Total"]));
		    }
		}

		if ((bank == 'all') & (parent == 'all')) {
			
			if (company == data.Company) {
			     output += '<tr><td class="name">' + data.Bank + '<span class="flag-icon flag-icon-' + data.Bank_Country_Code.toLowerCase() + '"></span></td><td class="number"> ' + year2021 + '</td><td class="number"> ' + year2022 + '</td><td class="number"> ' + year2023 + '</td><td class="number"> ' + year2024 + '</td><td class="number"> ' + year2025 + '</td><td class="number"> ' + grandTotal + '</td></tr>';
			    total = (total+parseInt(data["Total"]));
			}
		}

		if ((bank == 'all') & (company == 'all')) {
			if (parent == data.Company_Parent) {
			     output += '<tr><td class="name">' + data.Bank + '<span class="flag-icon flag-icon-' + data.Bank_Country_Code.toLowerCase() + '"></span></td><td class="number"> ' + year2021 + '</td><td class="number"> ' + year2022 + '</td><td class="number"> ' + year2023 + '</td><td class="number"> ' + year2024 + '</td><td class="number"> ' + year2025 + '</td><td class="number"> ' + grandTotal + '</td></tr>';
			    total = (total+parseInt(data["Total"]));
				uniqeClients.push(data.Company);
			}
		}
		
    });
	
    output += '</tbody></table></div>';

	var headerOutput = '';
    
    if ((company == 'all') & (parent == 'all')) {
		target = bank;
		headerOutput += '<div id="table-wrapper"><table id="full-data" class="tablesorter">'; 
		headerOutput += '<thead><tr class="table-header"><th class="fixed">Company</th><th class="number">2021</th><th class="number">2022</th><th class="number">2023</th><th class="number">2024</th><th class="number">2025</th><th class="number">Total</th></tr></thead><tbody>';
    } else if ((bank == 'all') & (parent == 'all')) {
		target = company;
		headerOutput += '<div id="table-wrapper"><table id="full-data">'; 
		headerOutput += '<thead><tr class="header"><th class="fixed">Bank</th><th class="number">2021</th><th class="number">2022</th><th class="number">2023</th><th class="number">2024</th><th class="number">2025</th><th class="number">Total</th></tr></thead><tbody>';
    } else if ((bank == 'all') & (company == 'all')) {
		target = parent;
		headerOutput += '<div id="table-wrapper"><table id="full-data">'; 
		headerOutput += '<thead><tr class="header"><th class="fixed">Bank</th><th class="number">2021</th><th class="number">2022</th><th class="number">2023</th><th class="number">2024</th><th class="number">2025</th><th class="number">Total</th></tr></thead><tbody>';
    }

	var finalOutput = headerOutput + output;
    jQuery("#output").append(finalOutput).ready(function() {
	   jQuery('table').tablesorter({sortList: [[8, 1]]});
	   jQuery("#profile-name").html(target);
	   jQuery(".total").html('Total Financing: $'+numberFormat(total)+ ' million USD');
	 //  jQuery("#profile-parents").html(getUnique(uniqeClients));
    });
	
}

// build the banks selector out of uniqe values in the object
function buildBankSelect(items) 
{
    var banks = [];
    jQuery.each(items, function(index, data) {
		    banks.push(data.Bank);
    });
    var uniquebanks = getUnique(banks);
    uniquebanks = uniquebanks.sort(Intl.Collator().compare);

	var select = '';
	jQuery.each(uniquebanks, function(index, data) {
		select += '<option value="'+data+'">'+data+'</option>';
	});
   jQuery("#banks-selector").append(select);

}
// build the companies selector out of uniqe values in the object
function buildCompanySelect(items) {

    var companies = [];
    jQuery.each(items, function(index, data) {
		    companies.push(data.Company);
    });
    var uniquecompanies = getUnique(companies);
    uniquecompanies = uniquecompanies.sort(Intl.Collator().compare);
    
	var select = '';
	jQuery.each(uniquecompanies, function(index, data) {
		select += '<option value="'+data+'">'+data+'</option>';
	});
   jQuery("#company-selector").append(select);

}

// build the parents selector out of uniqe values in the object
function buildParentSelect(items) {

    var parents = [];
    jQuery.each(items, function(index, data) {
		    parents.push(data.Company_Parent);
    });
    var uniqueparents = getUnique(parents);
    uniqueparents = uniqueparents.sort(Intl.Collator().compare);
    
	var select = '';
	jQuery.each(uniqueparents, function(index, data) {
		select += '<option value="'+data+'">'+data+'</option>';
	});
   jQuery("#parent-selector").append(select);

}


/* Company Profiles */

// get the data based on all data search param 

function getProfileData(target,profiles) {
	
	var result = '';
	jQuery.each( profiles, function( index, value )
    { 
		if (value.Company == target) {
			result = value;
		} 
    });
	//console.log(result);
	return result;
	
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
// put all the profile data on the page 
function buildProfileHeader(target,profiles) {

	var profile = getProfileData(target,profiles);
	
	if(profile && profile.Sectors != '') {

		var sectors = profile.Sectors.split(', ');
		var sector_list = '';
		//console.log(sectors);

		jQuery.each( sectors, function( index, value ) { 
			var sectorText = sectorNames(value);
			sector_list += '<div class="profile-sector-wrap"><div class="sectors '+value+'"></div><span>'+sectorText+'</span></div>';
		});
		jQuery("#profile-sectors").html('<h4>Sectors</h4>'+sector_list+'<div class="clear"></div>');
	} else {
		jQuery("#profile-sectors").html('');
	}

	if(profile && profile.Prize_details_1 != '') {
		jQuery("#profile-award").html('<div class="profile-prizes"><div class="profile-award-title">'+profile.Prize_details_1+'</div>');
		jQuery("#profile-deals").css('min-height','180px');
	} else {
		jQuery("#profile-award").html('');
		jQuery("#profile-deals").css('min-height','0');
	}

	// time for those deals
	var deals = '';
	jQuery("#profile-deals").html('');

	if (profile && ((profile.Dirty_deals != '') || (profile.Netzero != '') || (profile.Oil_gas != '') || (profile.Coal_policy != '') || (profile.Coal_exit != '') || (profile.Oil_gas_exit != '') || (profile.Reputational_risk != ''))) {
		if((profile.Dirty_deals != '') && (profile.Dirty_deals != null)) {
			deals += '<li><a href="'+profile.Dirty_deals+'">BankTrack Dodgy Deals Profile.</a></li>';
		}
		if((profile.Netzero != '') && (profile.Netzero != null)) {
			deals += '<li>Listed on the <a href="'+profile.Netzero+'">BankTrack NZBA tracker.</a></li>';
		}
		if((profile.Oil_gas != '') && (profile.Oil_gas != null)) {
			deals += '<li>Listed on the <a href="'+profile.Oil_gas+'">Global Oil and Gas Policy Tracker.</a></li>';
		}
		if((profile.Coal_policy != '') && (profile.Coal_policy != null)){
			deals += '<li>Listed on the <a href="'+profile.Coal_policy+'">Coal Policy Tracker.</a></li>';
		}
		if((profile.Coal_exit != '') && (profile.Coal_exit != null)){
			deals += '<li>Listed on the <a href="'+profile.Coal_exit+'">Global Coal Exit List.</a></li>';
		}
		if((profile.Oil_gas_exit != '') && (profile.Oil_gas_exit != null)){
			deals += '<li>Listed on the <a href="'+profile.Oil_gas_exit+'">Global Oil & Gas Exit List.</a></li>';
		}
		jQuery("#profile-deals").html('<ul id="profile-lists"><div class="case-label">Dig Deeper </div>'+deals+'</ul>').css('display','block');
	} else {
		jQuery("#profile-deals").css('display','none');
	}


	// reputational risk project
	var reputation = '';
	jQuery("#profile-reputation").html('');
	if(profile && (profile.Reputational_risk != '') && (profile.Reputational_risk != null)) {
		reputation += '<h4>Reputational Risk Project: <a href="'+profile.Reputational_risk_url+'">'+profile.Reputational_risk+'</a></h4>';
	}
	jQuery("#profile-reputation").html(reputation);

	// Time for the case studies 
	var cases = '';
	jQuery("#profile-cases").html('');
	
	/*
	if((profile.Case_title != '') && (profile.Case_title != null)) {
		cases += '<div class="case-label">Community Impacts of '+profile.Company+' Financing </div>';
	} */
	if(profile && (profile.Case_image != '') && (profile.Case_image != null)) {
		cases += '<div class="case-image"><a href="'+profile.Case_url+'"><img src="'+profile.Case_image+'"></a></div>';
	}
	if(profile && (profile.Case_title != '') && (profile.Case_title != null)) {
		cases += '<div class="case-label">Community Impacts of '+profile.Company+' Financing </div><div class="case-title"><a href="'+profile.Case_url+'">'+profile.Case_title+'</a></div><div class="profile-case-details"><strong>'+profile.Case_region+'</strong> - '+profile.Case_excerpt+'</div><div class="clear"></div></div>';
	}
	jQuery("#profile-cases").html('<div id="profile-case">'+cases+'</div>');
}

function buildFundingCompany(company,items) {
	var result = [];
	jQuery.each( items, function( index, data ) { 
		
		if(data.Bank == company) {
			result.push(data);
			
		} 
	});
	
	var data = fc_build_data(result);
	var categories = [company];
	//console.log(categories);
	fc_declare_single_chart(data,categories);
} 

/* Build CSV and Download */

function buildCSV(client, bank, parent, items) {
	var output = '';
	var total = 0;
	var csv = '';
	if (parent == null) { 
		jQuery.each( items, function( index, data ) {
			// make a few adjustments based on if this is a bank or client
			if (bank == data.Bank) {
				csv += data.Bank + ',' + data.Bank_Country_Code +  ','+ data.Company +  ',' + data.Company_Country_Code +  ',' + data.Company_Parent+  ',' + data["2020"] + ',' + data["2021"] + ',' + data["2022"] + ',' + data["2023"] + ',' + data["2024"] + ',' + data["2025"] + ',' + data["Total"]+'\n';
				total = (total+parseInt(data["Total"]));
			}
			if (client == data.Company) {
				csv += data.Bank + ',' + data.Bank_Country_Code+  ','+ data.Company +  ',' + data.Company_Country_Code +  ',' + data.Company_Parent+  ',' + data["2020"] + ',' + data["2021"] + ',' + data["2022"] + ',' + data["2023"] + ',' + data["2024"] + ',' + data["2025"] + ',' + data["Total"]+'\n';
				total = (total+parseInt(data["Total"]));
			}


		});
	} else {
		jQuery.each( items, function( index, data ) {
			if (parent == data.Company_Parent) {
				csv += data.Bank + ',' + data.Bank_Country_Code +  ',' + data.Company_Parent+  ',' + data["2020"] + ',' + data["2021"] + ',' + data["2022"] + ',' + data["2023"] + ',' + data["2024"] + ',' + data["2025"] + ',' + data["Total"]+'\n';
				total = (total+parseInt(data["Total"]));
			}

		});
	}
	// add some headers to the CSV
	var company = '';
	if(client != null) { 
		company = client;
		output += client+','+numberFormatCSV(total)+' million USD,,,,,,,,,,,\n';
	} else if (bank != null) { 
		company = bank;
		output += bank+','+numberFormatCSV(total)+' million USD,,,,,,,,,,,\n'; 
	} else if (parent != null) { 
		company = parent;
		output += parent +','+numberFormatCSV(total)+' million USD,,,,,,,,,,,\n'; 
	};      
	output += ',,,,,,,,,,,,\n';
	//ok now add the actual data
	if (parent != null) { 
		output += 'Bank,Bank_Country_Code,Company_Parent,2020,2021,2022,2023,2024,2025,Total\n';
	} else {
		output += 'Bank,Bank_Country_Code,Company,Company_Country_Code,Company_Parent,2020,2021,2022,2023,2024,2025,Total\n';
	}
	output += csv;

	//build the filname and run the download
	var date = new Date();
	download(company+'-'+date.toLocaleDateString()+'-'+date.toLocaleTimeString()+'.csv', output);
	
}
// initiate the download of the csv file
function download(filename, text) {
	var element = document.createElement('a');
	element.setAttribute('href', 'data:text/csv;charset=utf-8,%EF%BB%BF' + encodeURIComponent(text));
	element.setAttribute('download', filename);

	element.style.display = 'none';
	document.body.appendChild(element);

	element.click();

	document.body.removeChild(element);
}