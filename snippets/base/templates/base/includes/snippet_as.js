'use strict';

var SNIPPET_METRICS_SAMPLE_RATE = {{ settings.METRICS_SAMPLE_RATE }};
var SNIPPET_METRICS_URL = '{{ settings.METRICS_URL }}';
var ABOUTHOME_SHOWN_SNIPPET = null;
var USER_COUNTRY = null;
var GEO_CACHE_DURATION = 1000 * 60 * 60 * 24 * 30; // 30 days

// Start MozUITour
// Copy from https://hg.mozilla.org/mozilla-central/file/tip/browser/components/uitour/UITour-lib.js
if (typeof Mozilla == 'undefined') {
    var Mozilla = {};
}

if (typeof Mozilla.UITour == 'undefined') {
    Mozilla.UITour = {};
}

function _sendEvent(action, data) {
    var event = new CustomEvent('mozUITour', {
        bubbles: true,
        detail: {
            action: action,
            data: data || {}
        }
    });

    document.dispatchEvent(event);
}

Mozilla.UITour.showMenu = function(name, callback) {
    var showCallbackID;
    if (callback)
        showCallbackID = _waitForCallback(callback);

    _sendEvent('showMenu', {
        name: name,
        showCallbackID: showCallbackID
    });
};

Mozilla.UITour.hideMenu = function(name) {
    _sendEvent('hideMenu', {
        name: name
    });
};
// End MozUITour


(async function() {
    'use strict';

    // See https://github.com/mozilla/activity-stream/blob/master/docs/v2-system-addon/snippets.md
    // for documentation on the gSnippetsMap API

    {% if not preview %}
        // Fetch user country if we don't have it.
        if (!haveUserCountry()) {
            downloadUserCountry();
        }

        // Get the bookmarks count async
        setBookmarksCount();

        // If onboardingFinished is false, there may already be an onboarding snippet
        // shown so we cannot show a snippet. However, .disableOnboarding() can be
        // called so that it won't be shown on the *next* new tab
        if (gSnippetsMap.get("appData.onboardingFinished") === false) {
          return;
        }
    {% endif %}

    if (ABOUTHOME_SNIPPETS.length > 0) {
        ABOUTHOME_SHOWN_SNIPPET = chooseSnippet(ABOUTHOME_SNIPPETS);
    }

    if (ABOUTHOME_SHOWN_SNIPPET === null) {
        return;
    }

    // Hide snippets when the user disables snippets from the Preferences.
    window.addEventListener("Snippets:Disabled", () => {
        document.querySelector("#snippets-container").style.display = "none";
    });

    // Inject the snippet onto the page.
    var snippetElement = document.createElement('div');
    snippetElement.innerHTML = ABOUTHOME_SHOWN_SNIPPET.code;
    document.getElementById('snippets').appendChild(snippetElement);
    activateScriptTags(snippetElement);
    document.querySelector("#snippets-container").style.display = "block";

    // By the time show_snippet event reaches #snippets the snippet
    // will have finished initializing and altering the DOM. It's the
    // time to modifyLinks() and addSnippetBlockLinks().
    var snippets = document.getElementById('snippets');
    snippets.addEventListener('show_snippet', function(event) {
        var snippetsContainer = document.getElementById('snippets-container');
        // Add sample rate and snippet ID to currently displayed links.
        var parameters = ('sample_rate=' + SNIPPET_METRICS_SAMPLE_RATE + '&snippet_name=' +
                          ABOUTHOME_SHOWN_SNIPPET.id);
        modifyLinks(snippetsContainer.querySelectorAll('a'), parameters);
        addSnippetBlockLinks(snippetsContainer.querySelectorAll('.block-snippet-button'));
        sendImpression();
    });

    // Trigger show_snippet event
    var evt = document.createEvent('Event');
    evt.initEvent('show_snippet', true, true);
    snippetElement.querySelector('.snippet').dispatchEvent(evt);

    {% if preview %}
    function chooseSnippet(snippets) {
        return snippets[0];
    }
    {% else %}
    // Choose which snippet to display to the user based on various factors,
    // such as which country they are in.
    function chooseSnippet(snippets) {
        USER_COUNTRY = getUserCountry();
        if (USER_COUNTRY) {
            snippets = snippets.filter(
                function(snippet) {
                    var countries = snippet.countries;
                    if (countries.length && countries.indexOf(USER_COUNTRY) === -1) {
                        return false;
                    }
                    return true;
                }
            );
        }
        else {
            // If we don't have the user's country, remove all geolocated snippets.
            // Bug 1140476
            snippets = snippets.filter(
                function(snippet) {
                    return snippet.countries.length === 0;
                }
            );
        }

        // Filter Snippets based on Firefox Account existence.
        var has_fxaccount = gSnippetsMap.get('appData.fxaccount');
        if (has_fxaccount === true) {
            snippets = snippets.filter(
                function(snippet) {
                    return (snippet.client_options.has_fxaccount == 'yes' ||
                            snippet.client_options.has_fxaccount == 'any');
                }
            );
        } else if (has_fxaccount === false) {
            snippets = snippets.filter(
                function(snippet) {
                    return (snippet.client_options.has_fxaccount == 'no' ||
                            snippet.client_options.has_fxaccount == 'any');
                }
            );
        } else {
            snippets = snippets.filter(
                function(snippet) {
                    return (snippet.client_options.has_fxaccount == 'any');
                }
            );
        }

        // Filter Snippets based on appData.isDevtoolsUser
        var is_developer = gSnippetsMap.get('appData.isDevtoolsUser');
        if (is_developer === true) {
            snippets = snippets.filter(
                function(snippet) {
                    return (snippet.client_options.is_developer == 'yes' ||
                            snippet.client_options.is_developer == 'any');
                }
            );
        } else if (is_developer === false) {
            snippets = snippets.filter(
                function(snippet) {
                    return (snippet.client_options.is_developer == 'no' ||
                            snippet.client_options.is_developer == 'any');
                }
            );
        } else {
            snippets = snippets.filter(
                function(snippet) {
                    return (snippet.client_options.is_developer == 'any');
                }
            );
        }

        // Filter Snippets based on whether Firefox is the default browser or not.
        var defaultBrowser = gSnippetsMap.get('appData.defaultBrowser');
        if (defaultBrowser === true || defaultBrowser === undefined) {
            snippets = snippets.filter(
                function(snippet) {
                    return (snippet.client_options.is_default_browser == 'yes' ||
                            snippet.client_options.is_default_browser == 'any');
                }
            );
        } else {
            snippets = snippets.filter(
                function(snippet) {
                    return (snippet.client_options.is_default_browser == 'no' ||
                            snippet.client_options.is_default_browser == 'any');
                }
            );
        }

        // Exclude snippets from search providers.
        var selectedSearchEngine = gSnippetsMap.get('appData.selectedSearchEngine');
        if (selectedSearchEngine) {
            snippets = snippets.filter(
                function(snippet) {
                    var excludeFromSearchEngines = snippet.exclude_from_search_engines;
                    if (excludeFromSearchEngines.length &&
                        excludeFromSearchEngines.indexOf(selectedSearchEngine.searchEngineIdentifier) !== -1) {
                        return false;
                    }
                    return true;
                }
            );
        }
        else {
            // We don't have the search engine information yet. Remove all
            // snippets with search engine filtering.
            snippets = snippets.filter(
                function(snippet) {
                    return snippet.exclude_from_search_engines.length === 0;
                }
            );
        }

        // Filter based on Firefox version
        var userAgent = window.navigator.userAgent.match(/Firefox\/([0-9]+)\./);
        var firefox_version  = userAgent ? parseInt(userAgent[1]) : 0;
        if (firefox_version !== 0) {
            snippets = snippets.filter(
                function(snippet) {
                    var lower_bound = snippet.client_options.version_lower_bound;
                    var upper_bound = snippet.client_options.version_upper_bound;
                    if (lower_bound && lower_bound !== 'any') {
                        if (lower_bound === 'current_release') {
                            if (firefox_version !== CURRENT_RELEASE)
                                return false;
                        }
                        else {
                            if (firefox_version < lower_bound) {
                                return false;
                            }
                        }
                    }
                    if (upper_bound && upper_bound !== 'any') {
                        if (upper_bound === 'older_than_current_release') {
                            if (firefox_version >= CURRENT_RELEASE)
                                return false;
                        }
                        else {
                            if (firefox_version > upper_bound)
                                return false;
                        }
                    }
                    return true;
                });
        }

        // Filter based on screen resolution
        var verticalScreenResolution = screen.width;
        snippets = snippets.filter(
            function(snippet) {
                let snippetResolutions = snippet.client_options.screen_resolutions.split(';');
                let display = false;
                snippetResolutions.forEach(function(resolution) {
                    let minmax = resolution.split('-');
                    if (parseInt(minmax[0]) <= verticalScreenResolution
                        && verticalScreenResolution < parseInt(minmax[1])) {
                        display = true;
                        return;
                    }
                });
                return display;
            }
        );

        // Filter Snippets based on appData.previousSessionEnd
        var prevSessionEnd = gSnippetsMap.get('appData.previousSessionEnd');
        if (prevSessionEnd !== undefined) {
            // weeks (604800000 is num milliseconds in a week)
            var sessionEndWeeksAgo = (Date.now() - prevSessionEnd) / 604800000;
            snippets = snippets.filter(
                function(snippet) {
                    let lower_bound = snippet.client_options.sessionage_lower_bound;
                    let upper_bound = snippet.client_options.sessionage_upper_bound;
                    if (lower_bound > -1 && sessionEndWeeksAgo < lower_bound) {
                        return false;
                    }
                    if (upper_bound > -1 && sessionEndWeeksAgo >= upper_bound) {
                        return false;
                    }
                    return true;
                }
            );
        }
        else {
            // Remove all snippets that use session age since this information
            // is not available.
            snippets = snippets.filter(
                function(snippet) {
                    if (snippet.client_options.sessionage_lower_bound > -1
                        || snippet.client_options.sessionage_upper_bound > -1) {
                        return false;
                    }
                    return true;
                }
            );
        }

        // Filter based on Profile age
        //
        // profileCreatedWeeksAgo can be either undefined for Firefox
        // versions that don't expose this information, or a number >= 0.
        var profileCreatedWeeksAgo = gSnippetsMap.get('appData.profileCreatedWeeksAgo');
        if (profileCreatedWeeksAgo !== undefined) {
            snippets = snippets.filter(
                function(snippet) {
                    let lower_bound = snippet.client_options.profileage_lower_bound;
                    let upper_bound = snippet.client_options.profileage_upper_bound;
                    if (lower_bound > -1 && profileCreatedWeeksAgo < lower_bound) {
                        return false;
                    }
                    if (upper_bound > -1 && profileCreatedWeeksAgo >= upper_bound) {
                        return false;
                    }
                    return true;
                }
            );
        }
        else {
            // Remove all snippets that use profile age since this information
            // is not available.
            snippets = snippets.filter(
                function(snippet) {
                    if (snippet.client_options.profileage_lower_bound > -1
                        || snippet.client_options.profileage_upper_bound > -1) {
                        return false;
                    }
                    return true;
                }
            );
        }

        // Filter based on bookmarks count
        var total_bookmarks_count = gSnippetsMap.get('totalBookmarksCount');
        if (total_bookmarks_count !== undefined) {
            snippets = snippets.filter(
                function(snippet) {
                    let lower_bound = snippet.client_options.bookmarks_count_lower_bound;
                    let upper_bound = snippet.client_options.bookmarks_count_upper_bound;
                    if (lower_bound > -1 && total_bookmarks_count < lower_bound) {
                        return false;
                    }
                    if (upper_bound > -1 && total_bookmarks_count >= upper_bound) {
                        return false;
                    }
                    return true;
                });
        }
        else {
            // Remove all snippets that use bookmark count since this information
            // is not available.
            snippets = snippets.filter(
                function(snippet) {
                    if (snippet.client_options.bookmarks_count_lower_bound > -1
                        || snippet.client_options.bookmarks_count_upper_bound > -1) {
                        return false;
                    }
                    return true;
                }
            );
        }

        // Filter base on installed addons
        var installedAddons = gSnippetsMap.get('appData.addonInfo');
        if (installedAddons !== undefined) {
            snippets = snippets.filter(
                function(snippet) {
                    let addon_check = snippet.client_options.addon_check_type;
                    let addon_name = snippet.client_options.addon_name;
                    if (addon_check == 'any') {
                        return true;
                    }
                    else if (addon_check == 'installed' && addon_name in installedAddons) {
                        return true;
                    }
                    else if (addon_check == 'not_installed' && !(addon_name in installedAddons)) {
                        return true;
                    }
                    return false;
                }
            );
        }
        else {
            // Remove all snippets that use addon checks since this information
            // is not available.
            snippets = snippets.filter(
                function(snippet) {
                    if (snippet.client_options.addon_check_type === 'any') {
                        return true;
                    }
                    return false;
                }
            );
        }

        // Exclude snippets in block list.
        var blockList = getBlockList();
        snippets = snippets.filter(
            function (snippet) {
                var blockID = snippet.campaign || snippet.id;
                if (blockList.indexOf(blockID) === -1) {
                    return true;
                }
                return false;
            }
        );

        // Choose a random snippet from the snippets list.
        if (snippets && snippets.length) {
            var sum = 0;
            var number_of_snippets = snippets.length;
            for (var k = 0; k < number_of_snippets; k++) {
                sum += snippets[k].weight;
                snippets[k].weight = sum;
            }
            var random_number = Math.random() * sum;
            for (var k = 0; k < number_of_snippets; k++) {
                if (random_number < snippets[k].weight) {
                    return snippets[k];
                }
            }
        } else {
            return null;
        }
    }
    {% endif %}

    // Check whether we have the user's country stored and if it is still valid.
    function haveUserCountry() {
        // Check if there's an existing country code to use.
        if (gSnippetsMap.get('geoCountry')) {
            // Make sure we have a valid lastUpdated date.
            var lastUpdated = Date.parse(gSnippetsMap.get('geoLastUpdated'));
            if (lastUpdated) {
                // Make sure that it is past the lastUpdated date.
                var now = new Date();
                if (now < lastUpdated + GEO_CACHE_DURATION) {
                    return true;
                }
            }
        }

        return false;
    }

    function getUserCountry() {
        if (haveUserCountry()) {
            return gSnippetsMap.get('geoCountry');
        } else {
            return null;
        }
    }

    // Download the user's country using the geolocation service.
    // Please do not directly use this code or Snippets key.
    // Contact MLS team for your own credentials.
    // https://location.services.mozilla.com/contact
    function downloadUserCountry() {
        var GEO_URL = "{{ settings.GEO_URL }}";
        var request = new XMLHttpRequest();
        request.timeout = 60000;
        request.onreadystatechange = function() {
            if (request.readyState == 4 && request.status == 200) {
                var country_data = JSON.parse(request.responseText);

                try {
                    gSnippetsMap.set('geoCountry', country_data.country_code);
                    gSnippetsMap.set('geoLastUpdated', new Date());
                } catch (e) {
                    // Most likely failed to load Data file. Continue on without us,
                    // we'll try again next time.
                }
            }
        };
        request.open('GET', GEO_URL, true);
        request.send();
    }

    // Notifies stats server that the given snippet ID
    // was shown. No personally-identifiable information
    // is sent.
    function sendImpression() {
        sendMetric('impression');
    }

    // Modifies the given links to include the specified GET parameters.
    function modifyLinks(links, parameters) {
        for (var k = 0, len = links.length; k < len; k++) {
            var link = links[k];
            var delimeter = (link.href.indexOf('?') !== -1 ? '&' : '?');

            // Pull the fragment off of the link
            var fragment_position = link.href.indexOf('#');
            if (fragment_position === -1) {
                fragment_position = link.href.length;
            }

            var href = link.href.substring(0, fragment_position);
            var fragment = link.href.substring(fragment_position);

            link.href = href + delimeter + parameters + fragment;
        }
    }

    // Add links to buttons that block snippets.
    function addSnippetBlockLinks(elements) {
        var blockSnippet = function (event) {
            var metric;
            event.preventDefault();
            event.stopPropagation();
            metric = event.target.dataset.metric || 'snippet-blocked';
            sendMetric(metric);
            addToBlockList();

            // Hide #snippets-container for this tab.
            document.querySelector("#snippets-container").style.display = "none";
        };

        for (var k = 0; k < elements.length; k++) {
            var button = elements[k];
            button.addEventListener('click', blockSnippet);
        }
    }


    // Scripts injected by innerHTML are inactive, so we have to relocate them
    // through DOM manipulation to activate their contents.
    // (Adapted from http://mxr.mozilla.org/mozilla-central/source/browser/base/content/abouthome/aboutHome.js)
    function activateScriptTags(element) {
       Array.forEach(element.getElementsByTagName('script'), function(elt) {
           var relocatedScript = document.createElement('script');
           relocatedScript.type = 'application/javascript';
           relocatedScript.text = elt.text;
           elt.parentNode.replaceChild(relocatedScript, elt);
       });
    }

    // Listen for clicks on links and send metrics.
    var snippetsContainer = document.getElementById('snippets-container');
    snippetsContainer.addEventListener('click', function(event) {
        var callback;
        var metric;
        var target = event.target;
        while (target.tagName && target.tagName.toLowerCase() !== 'a') {
            // Do not track clicks outside snippets-container.
            if (target.id === 'snippets-container') {
                return;
            }
            target = target.parentNode;
        }

        if (target.href) {
            // First handle the special about:accounts links that call
            // showFirefoxAccounts method. Due to the special nature of
            // about:accounts we can only open in the same tab.
            if (target.href.indexOf('about:accounts') === 0) {
                event.preventDefault();
                callback = function() {
                    gSnippetsMap.showFirefoxAccounts();
                };
            }
            // Handle UITour showMenu appMenu
            else if (target.href.indexOf('uitour:showMenu:appMenu') === 0) {
                event.preventDefault();
                callback = function() {
                    Mozilla.UITour.showMenu('appMenu');
                };
                target.href = 'uitour:hideMenu:appMenu';
            }
            // Handle UITour hideMenu appMenu
            else if (target.href.indexOf('uitour:hideMenu:appMenu') === 0) {
                event.preventDefault();
                callback = function() {
                    Mozilla.UITour.hideMenu('appMenu');
                };
                target.href = 'uitour:showMenu:appMenu';
            }
            // If normal click (i.e. no new tab) and not counted, prevent
            // default to allow counting and re-trigger.
            else if (event.button === 0 &&
                     !(event.metaKey || event.ctrlKey) &&
                     target.dataset.eventCounted !== 'true') {
                event.preventDefault();
                callback = function() {
                    target.click();
                };
            }
        }

        // Count snippet clicks only one time.
        if (target.dataset.eventCounted !== 'true') {
            target.dataset.eventCounted = 'true';
            // Fetch custom metric or default to 'click'
            metric = target.dataset.metric || 'click';
            sendMetric(metric, callback, target.href);
        }
        // Call callback if defined, otherwise allow the click to propagate
        // freely.
        else if (callback) {
            callback();
        }
    }, false);
})();

// Send impressions and other interactions to the service
// If no parameter is entered, quit function
function sendMetric(metric, callback, href) {
    {# In preview mode, disable sampling, log metric, but do not send to service #}
    {% if preview %}
      console.log("[preview mode] Sending metric: " + metric);
      if (callback) {
          setTimeout(callback);
      }
      return;
    {% else %}

    if (!gSnippetsMap.get('appData.telemetryEnabled') || !SNIPPET_METRICS_URL ||
        !metric || (Math.random() > SNIPPET_METRICS_SAMPLE_RATE)) {
        if (callback) {
              // setTimeout is here because when metrics succeeds the callback is async.
              // When we don't use metrics, we should be consistent and
              // fire the callback async too.
              setTimeout(callback);
          }
          return;
      }

      var locale = '{{ locale }}';
      var userCountry = USER_COUNTRY || '';
      var campaign = ABOUTHOME_SHOWN_SNIPPET.campaign;
      var snippet_id = ABOUTHOME_SHOWN_SNIPPET.id;
      var snippet_full_name = ABOUTHOME_SHOWN_SNIPPET.name;

      var url = (SNIPPET_METRICS_URL + '?snippet_name=' + snippet_id +
                 '&snippet_full_name=' + snippet_full_name +
                 '&locale=' + locale + '&country=' + userCountry +
                 '&metric=' + metric + '&campaign=' + campaign);

      if (href) {
          url = url + "&href=" + escape(href);
      }

      var request = new XMLHttpRequest();
      request.open('GET', url);
      if (callback) {
          request.addEventListener('loadend', callback, false);
      }
      request.send();
      return request;
    {% endif %}
}

function popFromBlockList(snippetID) {
    var blockList = getBlockList();
    var item = blockList.pop(snippetID);
    gSnippetsMap.set('blockList', blockList);
    return item;
}

function addToBlockList(snippetID) {
    {# In preview mode just log blocking #}
    {% if preview %}
    console.log("[preview mode] Blocked snippet: " + snippetID);
    return;
    {% endif %}

    if (snippetID === undefined) {
        snippetID = ABOUTHOME_SHOWN_SNIPPET.campaign || ABOUTHOME_SHOWN_SNIPPET.id;
    }
    gSnippetsMap.blockSnippetById(snippetID);
}

function getBlockList() {
    if (gSnippetsMap.get('blockList') === undefined) {
        gSnippetsMap.set('blockList', []);
    }
    return gSnippetsMap.get('blockList');
}

async function setBookmarksCount() {
    gSnippetsMap.getTotalBookmarksCount().then(count => gSnippetsMap.set('totalBookmarksCount', count));
}
