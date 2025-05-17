if (static_path == undefined) {
  throw new Error("static_path has not been set.");
}

async function getSvgContent(path) {
  try {
      const response = await fetch(path);
      if (!response.ok) {
          throw new Error(`Error al cargar el SVG: ${response.statusText}`);
      }
      const svgContent = await response.text();
      return svgContent;
  } catch (error) {
      console.error('Error al obtener el SVG:', error);
      return null;
  }
}

let cache = {}

const svg = {
  "accountCircle": (static_path + "account_circle_24dp.svg"),
  "album": (static_path + "album_24dp.svg"),
  "explicit": (static_path + "explicit_24dp.svg"),
  "playArrow": (static_path + "play_arrow_24dp.svg"),
  "login": (static_path + "login_24dp.svg"),
  "search": (static_path + "search_24dp.svg"),
  "article": (static_path + "article_24dp.svg"),
  "close": (static_path + "close_24dp.svg"),
  "personAdd": (static_path + "person_add_24dp.svg"),
  "personRemove": (static_path + "person_remove_24dp.svg"),
  "skipPrevious": (static_path + "skip_previous_24dp.svg"),
  "skipNext": (static_path + "skip_next_24dp.svg"),
  "repeat": (static_path + "repeat_24dp.svg"),
  "repeatOne": (static_path + "repeat_one_24dp.svg")
};

async function loadSvgs() {
  const svgElements = document.querySelectorAll('svgload');

  for (let element of svgElements) {
      const name = element.getAttribute('name');

      if (name && svg[name]) {
          let svgContent;
          if(!cache[name]){
              cache[name] = getSvgContent(svg[name]);
          }
          svgContent = await cache[name];
          if (svgContent) {
            const parser = new DOMParser();
            const svgDoc = parser.parseFromString(svgContent, 'image/svg+xml');
            const svgElement = svgDoc.documentElement;

            const classList = element.classList;
            classList.forEach(cls => svgElement.classList.add(cls));

            element.replaceWith(svgElement);
          } else {
              console.warn(`SVG no encontrado para: ${name}`);
          }
      }
  }
}

window.addEventListener('DOMContentLoaded', loadSvgs);
