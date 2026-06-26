import 'vuetify/styles'
import './styles.css'

import { createPinia } from 'pinia'
import { createApp } from 'vue'
import { createVuetify } from 'vuetify'
import { aliases, mdi } from 'vuetify/iconsets/mdi-svg'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'

import App from './App.vue'
import { router } from './router'

const vuetify = createVuetify({
  components,
  directives,
  icons: {
    defaultSet: 'mdi',
    aliases,
    sets: { mdi }
  },
  theme: {
    defaultTheme: 'lan',
    themes: {
      lan: {
        dark: false,
        colors: {
          primary: '#176B87',
          secondary: '#5C8374',
          accent: '#DDA15E',
          background: '#F7F8F3',
          surface: '#FFFFFF',
          error: '#B42318'
        }
      }
    }
  }
})

createApp(App).use(createPinia()).use(router).use(vuetify).mount('#app')
