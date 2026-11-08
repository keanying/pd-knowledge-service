import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ViewUIPlus from 'view-ui-plus'
import './styles/theme.less'
import './styles/main.css'
import App from './App.vue'
import { router } from './router'
import { config } from './config'

document.title = config.title

createApp(App).use(createPinia()).use(router).use(ViewUIPlus).mount('#app')
