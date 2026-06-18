import React, { useState, useEffect, useRef } from 'react';
import { Input, Button, List, Avatar, Card, Spin, Empty, Tooltip, message } from 'antd';
import { 
  SendOutlined, 
  RobotOutlined, 
  UserOutlined, 
  DeleteOutlined, 
  PlusOutlined,
  MessageOutlined 
} from '@ant-design/icons';
import { motion, AnimatePresence } from 'framer-motion';
import { QwenPawClient, ChatMessage, ChatSession } from '../../services/qwenpaw-client';

const { TextArea } = Input;

interface ChatWidgetProps {
  userId: string;
  visible?: boolean;
}

export const ChatWidget: React.FC<ChatWidgetProps> = ({ userId }) => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [chats, setChats] = useState<ChatSession[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [currentChatId, setCurrentChatId] = useState<string | undefined>();
  const [isInitializing, setIsInitializing] = useState(true);
  
  const clientRef = useRef(new QwenPawClient(userId));
  const scrollRef = useRef<HTMLDivElement>(null);
  const messagesRef = useRef<ChatMessage[]>([]);

  // 初始化
  useEffect(() => {
    clientRef.current = new QwenPawClient(userId);
    initData();
  }, [userId]);

  const initData = async () => {
    setIsInitializing(true);
    try {
      const historyChats = await clientRef.current.listChats();
      setChats(historyChats);
      
      if (historyChats.length > 0) {
        const lastChat = historyChats[0];
        setCurrentChatId(lastChat.id);
        const history = await clientRef.current.getChatHistory(lastChat.id);
        setMessages(history);
      }
    } catch (err) {
      message.error('加载对话失败');
    } finally {
      setIsInitializing(false);
    }
  };

  // 滚动到底部
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
    messagesRef.current = messages;
  }, [messages]);

  const handleNewChat = async () => {
    try {
      const newChat = await clientRef.current.createChat('新对话');
      setChats([newChat, ...chats]);
      setCurrentChatId(newChat.id);
      setMessages([]);
    } catch (err) {
      message.error('创建会话失败');
    }
  };

  const handleSend = async () => {
    if (!input.trim() || loading) return;

    const userMsg: ChatMessage = { role: 'user', content: input };
    const tempInput = input;
    setInput('');
    setLoading(true);

    let chatId = currentChatId;
    if (!chatId) {
      try {
        const newChat = await clientRef.current.createChat();
        chatId = newChat.id;
        setCurrentChatId(chatId);
        setChats([newChat, ...chats]);
      } catch (err) {
        message.error('会话创建失败');
        setLoading(false);
        return;
      }
    }

    const nextMessages: ChatMessage[] = [
      ...messagesRef.current,
      userMsg,
      { role: 'assistant', content: '' },
    ];
    messagesRef.current = nextMessages;
    setMessages(nextMessages);

    await clientRef.current.sendMessage(tempInput, {
      chatId,
      onChunk: (chunk) => {
        const newMsgs = [...messagesRef.current];
        const lastIndex = newMsgs.length - 1;
        if (lastIndex < 0) return;
        const last = { ...newMsgs[lastIndex] };
        last.content += chunk;
        newMsgs[lastIndex] = last;
        messagesRef.current = newMsgs;
        setMessages(newMsgs);
      },
      onComplete: () => {
        setLoading(false);
      },
      onError: (err) => {
        message.error('发送失败: ' + (err.message || '未知错误'));
        setLoading(false);
      }
    });
  };

  if (isInitializing) {
    return <div style={{ display: 'flex', justifyContent: 'center', padding: '50px' }}><Spin /></div>;
  }

  return (
    <Card 
      className="copilot-chat-card"
      title={
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span><MessageOutlined /> AI 助手</span>
          <Tooltip title="新对话">
            <Button type="text" icon={<PlusOutlined />} onClick={handleNewChat} />
          </Tooltip>
        </div>
      }
      styles={{ body: { padding: 0, display: 'flex', flexDirection: 'column', height: '600px' } }}
    >
      <div 
        ref={scrollRef}
        className="chat-body"
        style={{ flex: 1, overflowY: 'auto', padding: '16px', backgroundColor: '#f5f5f5' }}
      >
        <AnimatePresence>
          {messages.length === 0 ? (
            <Empty description="开始一段对话吧" style={{ marginTop: '100px' }} />
          ) : (
            messages.map((m, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3 }}
                style={{
                  display: 'flex',
                  flexDirection: m.role === 'user' ? 'row-reverse' : 'row',
                  marginBottom: '16px',
                  gap: '8px'
                }}
              >
                <Avatar 
                  icon={m.role === 'user' ? <UserOutlined /> : <RobotOutlined />} 
                  style={{ backgroundColor: m.role === 'user' ? '#1890ff' : '#52c41a' }}
                />
                <div style={{
                  maxWidth: '80%',
                  padding: '10px 14px',
                  borderRadius: '12px',
                  backgroundColor: m.role === 'user' ? '#1890ff' : '#fff',
                  color: m.role === 'user' ? '#fff' : 'rgba(0, 0, 0, 0.85)',
                  boxShadow: '0 2px 4px rgba(0,0,0,0.05)',
                  whiteSpace: 'pre-wrap',
                  lineHeight: '1.6'
                }}>
                  {m.content}
                </div>
              </motion.div>
            ))
          )}
        </AnimatePresence>
        {loading && messages[messages.length-1]?.content === '' && (
          <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
            <Avatar icon={<RobotOutlined />} style={{ backgroundColor: '#52c41a' }} />
            <div style={{ padding: '10px', backgroundColor: '#fff', borderRadius: '12px' }}>
              <Spin size="small" />
            </div>
          </div>
        )}
      </div>

      <div style={{ padding: '16px', borderTop: '1px solid #f0f0f0', backgroundColor: '#fff' }}>
        <TextArea
          value={input}
          onChange={e => setInput(e.target.value)}
          placeholder="Ctrl + Enter 发送消息..."
          autoSize={{ minRows: 2, maxRows: 6 }}
          onPressEnter={e => {
            if (e.ctrlKey || e.metaKey) {
              handleSend();
            }
          }}
          disabled={loading}
          style={{ marginBottom: '8px' }}
        />
        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <Button 
            type="primary" 
            icon={<SendOutlined />} 
            onClick={handleSend}
            loading={loading}
          >
            发送
          </Button>
        </div>
      </div>
    </Card>
  );
};
