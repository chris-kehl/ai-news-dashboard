#!/usr/bin/env python3
"""Location-based feed configuration.

One-stop config for Reddit, X, and local-news RSS.  All lookups use _norm_key().
For locations not explicitly listed, the scrapers fall back to raw city/state name.
"""
import re


def _norm_key(s: str) -> str:
    """Lowercase, strip non-letters."""
    return re.sub(r"[^a-z]", "", s.lower())


def _raw_sub(name: str) -> str:
    """Normalize a city/state name for a subreddit name."""
    n = name.lower().strip()
    n = re.sub(r"['.'’]", "", n)
    n = re.sub(r"[^a-z0-9]", "", n)
    return n


# ---------------------------------------------------------------------------
# Reddit: location key -> list of known-good subreddits.
# If a location isn't listed here, the scraper falls back to the raw city/state.
# ---------------------------------------------------------------------------
PRIORITY_LOCATIONS = {
    # key format: "<city><state>" (e.g. "louisvillekentucky")
    # Keep sorted alphabetically by state for legibility.
    "birminghamaalabama":       ["Birmingham", "alabama"],
    "anchoragealaska":          ["alaska", "anchorage"],
    "phoenixarizona":           ["phoenix", "arizona"],
    "tucsonarizona":            ["Tucson", "arizona"],
    "littlerockarkansas":       ["LittleRock", "arkansas"],
    "losangelescalifornia":     ["LosAngeles", "California", "orangecounty"],
    "sandiegocalifornia":       ["SanDiego", "California"],
    "sanfranciscocalifornia":   ["sanfrancisco", "bayarea", "California"],
    "sacramentocalifornia":     ["Sacramento", "California"],
    "denvercolorado":           ["Denver", "Colorado", "boulder"],
    "hartfordconnecticut":      ["Connecticut"],
    "jacksonvilleflorida":      ["jacksonville", "florida"],
    "miamiflorida":             ["Miami", "florida"],
    "orlandoflorida":           ["orlando", "florida"],
    "tampaflorida":             ["tampa", "florida"],
    "atlantageorgia":           ["Atlanta", "Georgia"],
    "honoluluhawaii":           ["Hawaii", "Honolulu"],
    "boiseidaho":               ["Boise", "Idaho"],
    "chicagoillinois":          ["chicago", "illinois"],
    "indianapolisindiana":      ["indianapolis", "indiana"],
    "desmoinesiowa":            ["desmoines", "Iowa"],
    "wichitakansas":            ["wichita", "kansas"],
    "louisvillekentucky":       ["Louisville", "Kentucky"],
    "lexingtonkentucky":        ["Lexington", "Kentucky"],
    "neworleanslouisiana":      ["NewOrleans", "Louisiana"],
    "batonrougelouisiana":      ["BatonRouge", "Louisiana"],
    "portlandmaine":            ["PortlandME", "Maine"],
    "baltimoremaryland":        ["baltimore", "maryland"],
    "bostonmassachusetts":      ["boston", "massachusetts"],
    "detroitmichigan":          ["Detroit", "Michigan"],
    "minneapolisminnesota":     ["Minneapolis", "minnesota"],
    "jacksonmississippi":       ["mississippi", "JacksonMS"],
    "kansascitymissouri":       ["kansascity", "Missouri"],
    "stlouismissouri":          ["StLouis", "Missouri"],
    "helenamontana":            ["montana"],
    "omahanebraska":            ["Omaha", "Nebraska"],
    "lasvegasnevada":           ["LasVegas", "nevada"],
    "manchesternewhampshire":   ["newhampshire"],
    "newarknewjersey":          ["newjersey", "NewarkNJ"],
    "albuquerquenewmexico":     ["Albuquerque", "newmexico"],
    "newyorknewyork":           ["nyc", "newyork", "longisland"],
    "buffalonewyork":           ["Buffalo", "newyork"],
    "charlottenorthcarolina":   ["Charlotte", "NorthCarolina"],
    "raleighnorthcarolina":     ["raleigh", "triangle", "NorthCarolina"],
    "columbusohio":             ["Columbus", "Ohio"],
    "clevelandohio":            ["Cleveland", "Ohio"],
    "cincinnatiohio":           ["Cincinnati", "Ohio"],
    "oklahomacityoklahoma":     ["okc", "oklahoma"],
    "tulsaoklahoma":            ["Tulsa", "oklahoma"],
    "portlandoregon":           ["Portland", "oregon"],
    "philadelphiapennsylvania": ["Philadelphia", "Pennsylvania"],
    "pittsburghpennsylvania":   ["pittsburgh", "Pennsylvania"],
    "providencerhodeisland":    ["RhodeIsland", "providence"],
    "charlestonsouthcarolina":  ["Charleston", "southcarolina"],
    "columbiasouthcarolina":    ["ColumbiaSC", "southcarolina"],
    "nashvilletennessee":       ["Nashville", "Tennessee"],
    "austintexas":              ["Austin", "texas"],
    "dallastexas":              ["Dallas", "texas"],
    "houstontexas":             ["Houston", "texas"],
    "sanantoniotexas":          ["SanAntonio", "texas"],
    "fortworthtexas":           ["FortWorth", "texas"],
    "saltlakecityutah":         ["SaltLakeCity", "utah"],
    "seattlewashington":        ["Seattle", "WashingtonState"],
    "spokanewashington":        ["Spokane", "WashingtonState"],
    "milwaukeewisconsin":       ["milwaukee", "wisconsin"],
    "madisonwisconsin":         ["madisonwi", "wisconsin"],
    "cheyennewyoming":          ["wyoming"],
}


def get_subreddits(city: str, state: str) -> list:
    """Return known-good subreddits for a location, or fall back to raw city+state."""
    key = _norm_key(city) + _norm_key(state)
    if key in PRIORITY_LOCATIONS:
        return list(PRIORITY_LOCATIONS[key])
    # Fallback: raw city / state names
    raw_city = _raw_sub(city)
    raw_state = _raw_sub(state)
    subs = []
    if raw_city:
        subs.append(raw_city)
    if raw_state and raw_state != raw_city:
        subs.append(raw_state)
    return subs


# ---------------------------------------------------------------------------
# X / Twitter: extra search terms per state (used in addition to city/state)
# ---------------------------------------------------------------------------
STATE_X_KEYWORDS = {
    "alabama":      ["Alabama Football", "Auburn"],
    "arizona":      ["Cardinals", "Suns"],
    "arkansas":     ["Razorbacks"],
    "california":   ["Lakers", "49ers", "Giants"],
    "colorado":     ["Broncos", "Nuggets"],
    "connecticut":  ["UConn"],
    "districtofcolumbia": ["DC", "Capitol"],
    "florida":      ["Heat", "Gators"],
    "georgia":      ["Bulldogs", "Braves"],
    "idaho":        ["Boise State"],
    "illinois":     ["Cubs", "Bears"],
    "indiana":      ["Colts", "Pacers"],
    "iowa":         ["Hawkeyes"],
    "kansas":       ["Chiefs", "Jayhawks"],
    "kentucky":     ["UK Wildcats", "Louisville Cardinals"],
    "louisiana":    ["Saints", "LSU Tigers"],
    "maryland":     ["Ravens", "Orioles"],
    "massachusetts":["Red Sox", "Celtics"],
    "michigan":     ["Wolverines", "Lions"],
    "minnesota":    ["Vikings", "Timberwolves"],
    "mississippi":  ["Ole Miss"],
    "missouri":     ["Chiefs", "Cardinals"],
    "montana":      ["Griz"],
    "nebraska":     ["Cornhuskers"],
    "nevada":       ["Raiders", "Golden Knights"],
    "newhampshire": ["Dartmouth"],
    "newjersey":    ["Devils", "Rutgers"],
    "newmexico":    ["Lobos"],
    "newyork":      ["Yankees", "Knicks", "Giants"],
    "northcarolina":["Tar Heels", "Panthers"],
    "northdakota":  ["NDSU"],
    "ohio":         ["Buckeyes", "Browns"],
    "oklahoma":     ["Thunder", "Sooners"],
    "oregon":       ["Ducks", "Trail Blazers"],
    "pennsylvania": ["Steelers", "Eagles"],
    "rhodeisland":  ["URI"],
    "southcarolina":["Gamecocks", "Clemson"],
    "southdakota":  ["SDSU"],
    "tennessee":    ["Titans", "Predators", "Volunteers"],
    "texas":        ["Longhorns", "Cowboys", "Astros"],
    "utah":         ["Jazz", "Utes"],
    "vermont":      ["UVM"],
    "virginia":     ["UVA", "Commanders"],
    "washington":   ["Seahawks", "Mariners"],
    "westvirginia": ["WVU"],
    "wisconsin":    ["Packers", "Bucks"],
    "wyoming":      ["Wyoming Cowboys"],
}


def get_x_queries(city: str, state: str) -> list:
    """Return extra X search keywords for the given state."""
    ns = _norm_key(state)
    return list(STATE_X_KEYWORDS.get(ns, []))


# ---------------------------------------------------------------------------
# Local-news RSS: verified / popular feeds per state.
# Only include feeds that are known to resolve; prune dead ones.
# ---------------------------------------------------------------------------
STATE_NEWS_FEEDS = {
    "alabama":      [("AL.com",                "https://www.al.com/rss/")],
    "arizona":      [("Arizona Republic",      "https://www.azcentral.com/rss/")],
    "california":   [("LA Times",              "https://www.latimes.com/rss2.0.xml"),
                     ("SF Chronicle",          "https://www.sfchronicle.com/rss/")],
    "colorado":     [("Denver Post",           "https://www.denverpost.com/rss/")],
    "connecticut":  [("CT Mirror",             "https://ctmirror.org/feed/")],
    "florida":      [("Miami Herald",          "https://www.miamiherald.com/rss/"),
                     ("Orlando Sentinel",      "https://www.orlandosentinel.com/rss/")],
    "georgia":      [("AJC",                   "https://www.ajc.com/rss/")],
    "illinois":     [("Chicago Tribune",       "https://www.chicagotribune.com/rss")],
    "indiana":      [("Indy Star",             "https://www.indystar.com/rss/")],
    "iowa":         [("Des Moines Register",   "https://www.desmoinesregister.com/rss/")],
    "kansas":       [("Wichita Eagle",         "https://www.kansas.com/rss/")],
    "kentucky":     [("WFPL NPR",              "https://wfpl.org/feed/"),
                     ("Kentucky Sports Radio", "https://kentuckysportsradio.com/feed/"),
                     ("Forward Kentucky",      "https://forwardky.com/feed/"),
                     ("The Lane Report",       "https://www.lanereport.com/feed/"),
                     ("UK Kernel",             "https://www.kykernel.com/feed/")],
    "louisiana":    [("NOLA.com",              "https://www.nola.com/rss/")],
    "maryland":     [("Baltimore Sun",         "https://www.baltimoresun.com/rss/")],
    "massachusetts":[("Boston Globe",          "https://www.bostonglobe.com/rss/"),
                     ("WBUR",                  "https://www.wbur.org/feed")],
    "michigan":     [("Detroit Free Press",    "https://www.freep.com/rss/")],
    "minnesota":    [("Star Tribune",          "https://www.startribune.com/rss/")],
    "missouri":     [("KCUR NPR",              "https://www.kcur.org/feed"),
                     ("St Louis P-D",          "https://www.stltoday.com/rss/")],
    "nebraska":     [("Omaha World-Herald",    "https://www.omaha.com/rss/")],
    "nevada":       [("Las Vegas RJ",          "https://www.reviewjournal.com/feed/")],
    "newhampshire": [("Union Leader",          "https://www.unionleader.com/rss/")],
    "newjersey":    [("NJ.com",                "https://www.nj.com/rss/"),
                     ("Star-Ledger",           "https://www.nj.com/starledger/rss/")],
    "newmexico":    [("ABQ Journal",           "https://www.abqjournal.com/feed/")],
    "newyork":      [("NY Daily News",         "https://www.nydailynews.com/rss/nydnrss.xml"),
                     ("NY Post",               "https://nypost.com/feed/")],
    "northcarolina":[("Charlotte Observer",    "https://www.charlotteobserver.com/rss/"),
                     ("WRAL",                  "https://www.wral.com/news/rss/")],
    "ohio":         [("Cleveland.com",         "https://www.cleveland.com/rss/")],
    "oklahoma":     [("Tulsa World",           "https://tulsaworld.com/rss/")],
    "oregon":       [("Oregonian",             "https://www.oregonlive.com/rss/")],
    "pennsylvania": [("Philly Inquirer",       "https://www.inquirer.com/rss/"),
                     ("Pittsburgh PG",         "https://www.post-gazette.com/rss/")],
    "rhodeisland":  [("Providence Journal",    "https://www.providencejournal.com/rss/")],
    "southcarolina":[("Post & Courier",        "https://www.postandcourier.com/rss/")],
    "tennessee":    [("WKRN Nashville",        "https://www.wkrn.com/feed/"),
                     ("Tennessean",            "https://www.tennessean.com/rss/")],
    "texas":        [("Texas Tribune",         "https://www.texastribune.org/feeds/all/"),
                     ("Houston Chronicle",     "https://www.houstonchronicle.com/rss/")],
    "utah":         [("SLTrib",                "https://www.sltrib.com/rss/")],
    "virginia":     [("Richmond TD",           "https://richmond.com/rss/")],
    "washington":   [("Seattle Times",         "https://www.seattletimes.com/feed/"),
                     ("KOMO News",             "https://komonews.com/feed")],
    "westvirginia": [("Charleston Gazette",    "https://www.wvgazettemail.com/rss/")],
    "wisconsin":    [("Milwaukee JS",          "https://www.jsonline.com/rss/")],
}


def get_news_feeds(state: str) -> list:
    """Return list of (label, url) RSS feeds for a state."""
    return list(STATE_NEWS_FEEDS.get(_norm_key(state), []))
