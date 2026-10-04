jQuery(window).load(function () {
	jQuery('.fa-search').click(function(e){
		e.stopPropagation();
	});
	jQuery('#menu-search').click(function(e){
		e.stopPropagation();
	});
	jQuery('.fa-search').click(function(e) {
		jQuery('#menu-search').toggle();
	});
	jQuery(".issue-understory-img").mouseenter(function() {
		jQuery(this).children(".blog-overlay").fadeIn();
	})
	.mouseleave(function() {
	    jQuery(this).children(".blog-overlay").fadeOut();
	});
	jQuery(".issue-understory-img").focusin(function() {
		jQuery(this).children(".blog-overlay").fadeIn();
	})
	.focusout(function() {
	    jQuery(this).children(".blog-overlay").fadeOut();
	});
	
	jQuery(".content-image-wrap .image").mouseenter(function() {
		jQuery(this).children(".blog-overlay").fadeIn();
	})
	.mouseleave(function() {
	    jQuery(this).children(".blog-overlay").fadeOut();
	});
	jQuery(".content-image-wrap .image").focusin(function() {
		jQuery(this).children(".blog-overlay").fadeIn();
	})
	.focusout(function() {
	    jQuery(this).children(".blog-overlay").fadeOut();
	});
	jQuery('#ss-floating-bar').css('opacity', '0');
	
	jQuery('.take-action-block a').click( function(e){
		if (jQuery(window).width() > 800) { 
			e.preventDefault();
			var url = jQuery(this).attr("href");
			jQuery('#responsive-iframe iframe').attr('src', url);
			jQuery('#iframe-container').css('display','block');
		}
	});
	
	jQuery('#iframe-container').click( function(){
		jQuery('#iframe-container').css('display','none');
		jQuery('#responsive-iframe iframe').attr('src', '');
	});
	
	jQuery('a.revel-button').click( function(e){
		if (jQuery(window).width() > 800) { 
			e.preventDefault();
			var url = jQuery(this).attr("href");
			jQuery('.page-video-test-page #responsive-iframe iframe').attr('src', url);
			jQuery('.page-video-test-page #iframe-container').css('display','block');
		}
	});
	
	jQuery('.page-video-test-page #iframe-container').click( function(){
		jQuery('.page-video-test-page #iframe-container').css('display','none');
		jQuery('.page-video-test-page #responsive-iframe iframe').attr('src', '');
	});
	
	/* temporary code for the EOY takeover stuff */
	/*jQuery('#pum-8889').on('pumBeforeOpen', function () {
        var $video = jQuery('video', jQuery(this));
        $video[0].play();
    });*/
    /*
	if (typeof jQuery.cookie('pum-8889') != 'undefined'){ 
		jQuery("#bobble").css('display', 'block');
		eoy_scroll_watcher();
	} 
	 jQuery('.pum-close').click(function(){
		jQuery("#bobble").css('display', 'block');
		eoy_scroll_watcher();
	}); */

	/* widow fix */
		
	jQuery(".understory-featured-image h1.block-headline").each(function() {
	  var wordArray = jQuery(this).text().split(" ");
	  if (wordArray.length > 1) {
	    wordArray[wordArray.length-2] += "&nbsp;" + wordArray[wordArray.length-1];
	    wordArray.pop();
	    jQuery(this).html(wordArray.join(" "));
	  }
	});
	jQuery('.site-footer .covid').hover(function(){
		jQuery('#eegg').toggle("slow");
	});

});
jQuery(document).on('click','.navbar-collapse',function(e) {
    if( jQuery(e.target).is('a') ) {
        jQuery(this).collapse('hide');
    }
});

/* temporary code for Big Give */

	var images = ['https://www.ran.org/wp-content/uploads/2021/05/Give-Big-2021_lightbox_Tarsier.png',
					'https://www.ran.org/wp-content/uploads/2021/05/Give-Big-2021_lightbox_Leopard.png',
					'https://www.ran.org/wp-content/uploads/2020/04/Give-Big-2020-lightbox.png'];
	jQuery(function () {
        var i = 0;
        jQuery("#popmake-8889 img").attr("src", images[i]);
        setInterval(function () {
            i++;
            if (i == images.length) {
                i = 0;
            }
            jQuery("#popmake-8889 img").attr("src", images[i]);
        }, 6000);
    });

 /* temporary code for the EOY takeover stuff 
 
 function eoy_scroll_watcher() {
	 jQuery(document).scroll(function() {
		  var y = jQuery(this).scrollTop();
		  
		  if (y > 350) {
		    eoy_slide_up();
		  } 
		  if (y < 350) {
		    eoy_slide_down();
		  }
		});
 }
function eoy_slide_up() {
	jQuery("#bobble").stop().animate({
        height: '200px'
    }, 700, 'swing');
    jQuery("body").css('margin-bottom', '190px');
    jQuery("body.home").css('margin-bottom', '0');
}

function eoy_slide_down() {
	jQuery("#bobble").stop().animate({
        height: '0px'
    }, 500, 'swing');
     jQuery("body").css('margin-bottom', '0px');
     jQuery("body.home").css('margin-bottom', '0');
}

*/

jQuery(document).scroll(function() {
  var y = jQuery(this).scrollTop();
  if (y > 450) {
    jQuery('#ss-floating-bar').css('opacity', '1');
  } else {
    jQuery('#ss-floating-bar').css('opacity', '0');
  }
});

