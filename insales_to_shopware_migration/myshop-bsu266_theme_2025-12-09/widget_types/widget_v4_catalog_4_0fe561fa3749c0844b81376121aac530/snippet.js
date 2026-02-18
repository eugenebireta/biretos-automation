$(function() {
  var isTouch = !!('ontouchstart' in window || navigator.msMaxTouchPoints);
  var infinityProductsTempPage = [];

  if (isTouch) {
    $(widget).find(".product-preview").addClass("is-touch");
  }

  $widget.each(function(index, el) {
    new LazyLoad({
      container: $(el).get(0),
      elements_selector: '.lazyload',
      use_native: 'loading' in document.createElement('img')
    });
  });

  function loadMoreCollectionProducts(productListBlock, showMoreBtn) {
    let next_page = productListBlock.data('collectionInfinity');

    if (next_page && next_page != '') {
      if (infinityProductsTempPage.indexOf(next_page) > -1) {
        return;
      }

      infinityProductsTempPage.push(next_page);
      showMoreBtn.addClass('is-loading');

      $.ajax({
        url: next_page,
        dataType: 'html'
      })
        .done(function(resultDom) {
          let new_products = $(resultDom).find('[data-collection-infinity]');
          let next = new_products.data('collectionInfinity');

          productListBlock.append( new_products.html() );
          productListBlock.data('collectionInfinity', next);

          productListBlock.find('[data-product-id]').each(function(index, el) {
            Products.initInstance($(el));
          });

          productListBlock.each(function(index, el) {
            new LazyLoad({
              container: $(el).get(0),
              elements_selector: '.lazyload',
              use_native: 'loading' in document.createElement('img')
            });
          });

          if (productListBlock.data('collectionInfinity') == '') {
            showMoreBtn.parents(".layout").hide();
          }
        })
        .always(function() {
          showMoreBtn.removeClass('is-loading');
        })
    }
  }

  $(function() {
  /* SHOW MODAL PREVIEW */

    EventBus.subscribe('change_variant:insales:product', function(data) {
      let is_product_instance_in_modal_panel = !!$(data.action.product[0]).parents(".modal-product-preview.is-open").length;

      if (data.action && data.action.product && data.first_image.url && is_product_instance_in_modal_panel) {
        let product_node = $(data.action.product[0]);
        product_node.find(".product-preview__photo img").attr("src", data.first_image.medium_url);
      }
    });

    EventBus.subscribe('load-more-products:insales:site', function(data) {
      let product_list_block = $widget.find("[data-collection-infinity]");
      let btn = $(data.event_target);

      loadMoreCollectionProducts(product_list_block, btn);
    });
  });

  if (window.location.pathname == '/favorites') {
    EventBus.subscribe('remove_item:insales:favorites_products', (data) => {
      $widget.find('[data-product-id="' + data.action.item + '"]').remove();
      if (data.products.length == 0 ) {
        $widget.find('.empty-catalog-message').removeClass('hidden');
      }
    })
  }
});
