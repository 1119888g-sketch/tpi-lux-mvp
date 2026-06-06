const menuToggle = document.querySelector('[data-menu-toggle]');
const mainNav = document.querySelector('.main-nav');
const contactForm = document.querySelector('.contact-form');

if (menuToggle && mainNav) {
  menuToggle.addEventListener('click', () => {
    mainNav.classList.toggle('is-open');
  });

  mainNav.addEventListener('click', (event) => {
    if (event.target instanceof HTMLAnchorElement) {
      mainNav.classList.remove('is-open');
    }
  });
}

if (contactForm) {
  contactForm.addEventListener('submit', (event) => {
    event.preventDefault();
    const button = contactForm.querySelector('button');
    if (!button) return;

    const originalText = button.textContent;
    button.textContent = 'Заявка зафиксирована в MVP';
    button.disabled = true;

    window.setTimeout(() => {
      button.textContent = originalText;
      button.disabled = false;
    }, 2600);
  });
}
