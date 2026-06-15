const menuToggle = document.querySelector('[data-menu-toggle]');
const mainNav = document.querySelector('.main-nav');
const contactForm = document.querySelector('.contact-form');

const heroVideo = document.querySelector('video.hero-image');
if (heroVideo && window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
  heroVideo.removeAttribute('autoplay');
  heroVideo.pause();
}

if (menuToggle && mainNav) {
  const setExpanded = (open) => {
    menuToggle.setAttribute('aria-expanded', String(open));
    menuToggle.setAttribute('aria-label', open ? 'Закрыть меню' : 'Открыть меню');
  };

  menuToggle.addEventListener('click', () => {
    const open = mainNav.classList.toggle('is-open');
    setExpanded(open);
  });

  mainNav.addEventListener('click', (event) => {
    if (event.target instanceof HTMLAnchorElement) {
      mainNav.classList.remove('is-open');
      setExpanded(false);
    }
  });
}

if (contactForm) {
  contactForm.addEventListener('submit', (event) => {
    event.preventDefault();
    const button = contactForm.querySelector('button');
    if (!button) return;

    const originalText = button.textContent;
    button.textContent = 'Заявка принята — мы свяжемся с вами';
    button.disabled = true;

    window.setTimeout(() => {
      button.textContent = originalText;
      button.disabled = false;
    }, 2600);
  });
}
