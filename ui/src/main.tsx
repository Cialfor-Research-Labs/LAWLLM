import {StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
import App from './App.tsx';
import ChatPage from './experimental-chat/ChatPage.tsx';
import './index.css';

const isExperimentalChat = window.location.pathname === '/experimental-chat';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {isExperimentalChat ? <ChatPage /> : <App />}
  </StrictMode>,
);
