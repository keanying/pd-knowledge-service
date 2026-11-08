import { createApp } from 'vue'
import './styles.css'
import App from './App.vue'

document.title = window.__PDA_CONFIG__?.title || '智能助手'
createApp(App).mount('#app')
