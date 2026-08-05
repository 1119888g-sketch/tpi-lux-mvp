const menuToggle = document.querySelector('[data-menu-toggle]');
const mainNav = document.querySelector('.main-nav');
const contactForm = document.querySelector('.contact-form');

const heroVideo = document.querySelector('video.hero-image');
if (heroVideo) {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    heroVideo.removeAttribute('autoplay');
    heroVideo.pause();
  } else {
    // Явный запуск: iOS/мобильные часто не стартуют autoplay без вызова play()
    const startHero = () => {
      const attempt = heroVideo.play();
      if (attempt && typeof attempt.catch === 'function') {
        attempt.catch(() => {
          // Автоплей заблокирован (Low Power / экономия трафика) — запустим по первому касанию
          const resume = () => {
            heroVideo.play().catch(() => {});
            document.removeEventListener('touchstart', resume);
            document.removeEventListener('click', resume);
          };
          document.addEventListener('touchstart', resume, { once: true, passive: true });
          document.addEventListener('click', resume, { once: true });
        });
      }
    };
    if (heroVideo.readyState >= 2) {
      startHero();
    } else {
      heroVideo.addEventListener('loadeddata', startHero, { once: true });
    }
  }
}

if (menuToggle && mainNav) {
  const setExpanded = (open) => {
    menuToggle.setAttribute('aria-expanded', String(open));
    menuToggle.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
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

const langSwitch = document.querySelector('[data-lang-switch]');
if (langSwitch) {
  const trigger = langSwitch.querySelector('.lang-current');

  const setOpen = (open) => {
    langSwitch.classList.toggle('is-open', open);
    if (trigger) trigger.setAttribute('aria-expanded', String(open));
  };

  if (trigger) {
    trigger.addEventListener('click', (event) => {
      event.stopPropagation();
      setOpen(!langSwitch.classList.contains('is-open'));
    });
  }

  // Клик мимо и Esc закрывают список — иначе он залипает на тач-устройствах.
  document.addEventListener('click', (event) => {
    if (!langSwitch.contains(event.target)) setOpen(false);
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && langSwitch.classList.contains('is-open')) {
      setOpen(false);
      if (trigger) trigger.focus();
    }
  });
}
