// "More" prompt: a pill with a bobbing down arrow at the bottom of anything that scrolls, shown while there's
// more to read below. Clicking it scrolls on by most of a screen. Used by the map panel and the API keys page.
"use strict";

function addMoreHint(scroller) {
  const page = scroller === document.scrollingElement;
  const pill = document.createElement("button");
  pill.type = "button";
  pill.className = "more-hint";
  pill.innerHTML = 'More <svg viewBox="0 0 12 12" aria-hidden="true"><path d="M2 4l4 4 4-4"/></svg>';
  pill.setAttribute("aria-label", "Scroll down for more");
  pill.hidden = true;
  if (page) {
    pill.classList.add("fixed");
    document.body.appendChild(pill);
  } else {
    const holder = document.createElement("div");   // sticks to the bottom of the box without taking room
    holder.className = "more-holder";
    holder.appendChild(pill);
    scroller.appendChild(holder);
  }

  const update = () => {
    const left = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight;
    const hide = left < 24 || scroller.clientHeight < 80;
    if (pill.hidden !== hide) pill.hidden = hide;   // only on change: setting it is itself a mutation we watch
  };
  pill.addEventListener("click", () => scroller.scrollBy({ top: scroller.clientHeight * 0.75, behavior: "smooth" }));
  (page ? window : scroller).addEventListener("scroll", update, { passive: true });
  window.addEventListener("resize", update);
  // content comes and goes (agency lists, cards, opened sections), so watch for that too
  new MutationObserver(() => requestAnimationFrame(update))
    .observe(page ? document.body : scroller, { childList: true, subtree: true, attributes: true, characterData: true });
  update();
  return update;
}
