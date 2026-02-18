/* eslint-disable linebreak-style */
var mobilePoint = 768;

function getWidget(item) {
  return item.closest('.layout');
}

$(document).ready(function() {
  $widget.each(function(index, el) {
    new LazyLoad({
      container: $(el).get(0),
      elements_selector: '.lazyload'
    });
  });

  if ($(window).width() >= mobilePoint) {
    $(widget).find(".js-cut-list").cutList({
      moreBtnTitle: '<span class="icon-ellipsis-h"></span>',
      alwaysVisibleElem: '.is-current'
    });
  }

  $(window).on('load', function() {
    $(widget).find(".js-cut-list").resize();
  });

  $(window).on('resize', function() {
    let collections_menu = $(widget).find(".header__collections");
    let collections_menu_content = collections_menu.find(".header__collections-content");

    if (collections_menu.is(".is-show")) {
      let max_height = $(window).height() - collections_menu.offset().top - 20;
      collections_menu_content.css("maxHeight", max_height);
    }
  });

  if ($(widget).find(".header__collections .is-current").length) {
    $(widget).find(".header__collections .is-current").addClass("is-show-mobile");
    $(widget).find(".header__collections > .header__collections-item.is-current").addClass("is-show");
  }

  $(widget).find(".js-show-header-collections").on("click", function() {
    let thisWidget = getWidget($(this));

    thisWidget.each(function(index, el) {
      let lazyLoadCollectionList = new LazyLoad({
        container: $(el).get(0),
        elements_selector: '.lazyload'
      });

      try {
        lazyLoadCollectionList.loadAll()
      } catch (e) {
        console.log(e)
      }
    });

    let collections_menu = thisWidget.find(".header__collections");
    let collections_menu_content = collections_menu.find(".header__collections-content");

    if (collections_menu.is(".is-show")) {
      collections_menu.removeClass("is-show");
    } else {
      collections_menu.addClass("is-show");

      let max_height = $(window).height() - collections_menu.offset().top - 20;
      collections_menu_content.css("maxHeight", max_height);
    }

    $(this).toggleClass("is-active");
    thisWidget.find(".header__collections-overlay").toggleClass("is-show");
  });

  $(document).on("click", function(event) {
    let thisWidget = getWidget($(event.target).closest('.layout'));

    if ($(event.target).closest(".js-show-header-collections").length || $(event.target).closest(".header__collections-content").length) {
      return;
    }

    thisWidget.find(".header__collections.is-show").removeClass("is-show");
    thisWidget.find(".header__collections-overlay.is-show").removeClass("is-show");
    thisWidget.find(".js-show-header-collections").removeClass("is-active");
  });

  $(widget).find(".js-show-mobile-submenu").on("click", function() {
    $(this).parents(".header__collections-item:first").toggleClass("is-show-mobile");
  });

  $(widget).find(".js-show-mobile-menu").on("click", function() {
    let thisWidget = getWidget($(this));

    thisWidget.find(".header").addClass("is-show-mobile");
  });

  $(widget).find(".js-hide-mobile-menu").on("click", function() {
    let thisWidget = getWidget($(this));

    thisWidget.find(".header").removeClass("is-show-mobile");
  });

  $(widget).find(".js-show-mobile-search").on("click", function() {
    $(this).parents(".header__search").toggleClass("is-show-mobile").find(".header__search-field").focus();
  });

  $(widget).find(".js-show-more-subcollections").on("click", function() {
    let thisWidget = getWidget($(this));

    let collections_menu = thisWidget.find(".header__collections-menu");
    let limit = collections_menu.attr("data-subcollections-items-limit");
    let collection_elem = $(this).parents(".header__collections-item.is-level-1");

    if ($(this).is(".is-active")) {
      $(this).removeClass("is-active");
      collection_elem.find('.header__collections-submenu .header__collections-item:nth-child(n+' + (parseInt(limit) + 1) + ')').addClass("is-hide");
    } else {
      $(this).addClass("is-active");
      collection_elem.find(".header__collections-submenu .header__collections-item").removeClass("is-hide");
    }
  });
});

EventBus.subscribe('widget:input-setting:insales:system:editor', (data) => {
  $(widget).find(".js-cut-list").resize();

  if (data.setting_name == 'subcollections-items-limit') {
    configureSubcollectionsItemsLimit(data.value);
  }
});

EventBus.subscribe('widget:change-setting:insales:system:editor', (data) => {
  $(widget).find(".js-cut-list").resize();

  if (data.setting_name == 'subcollections-items-limit') {
    configureSubcollectionsItemsLimit(data.value);
  }
});

function configureSubcollectionsItemsLimit(limit) {
  let collections_menu = $(widget).find(".header__collections-menu");
  collections_menu.attr("data-subcollections-items-limit", limit);

  $(widget).find(".header__collections-submenu").each(function() {
    let collection_elem = $(this).parents(".header__collections-item.is-level-1");
    let collection_elem_more_controls = collection_elem.find(".header__collections-show-more");

    $(this).find(".header__collections-item").removeClass("is-hide");
    $(this).find('.header__collections-item:nth-child(n+' + (parseInt(limit) + 1) + ')').addClass("is-hide");
    collection_elem_more_controls.find(".js-show-more-subcollections").removeClass("is-active");

    if ($(this).find(".header__collections-item").length > parseInt(limit)) {
      collection_elem_more_controls.addClass("is-show");
    } else {
      collection_elem_more_controls.removeClass("is-show");
    }
  });
}

$(widget).find(".js-toggle-languages-list").on("click", function() {
  $(this).parents(".header__languages").toggleClass("is-show");
});
