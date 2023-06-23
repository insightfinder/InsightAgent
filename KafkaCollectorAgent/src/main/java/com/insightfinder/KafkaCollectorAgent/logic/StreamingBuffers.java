package com.insightfinder.KafkaCollectorAgent.logic;

public class StreamingBuffers {
    final static int[] sizeTable = {9, 99, 999, 9999, 99999, 999999, 9999999,
            99999999, 999999999};
    boolean isSending;
    private int bufferSize;
    private StringBuffer stringBuffer;
    public StreamingBuffers() {
    }
    public StreamingBuffers(int bufferSize) {
        this.bufferSize = bufferSize;
        stringBuffer = new StringBuffer(bufferSize);
    }

    private static BufferHeader generateBufferHeader(String bufferStr) {
        BufferHeader bufferHeader = new BufferHeader();
        char[] pre = new char[2];
        pre[0] = '#';
        pre[1] = (char) ('0' + stringSize(bufferStr.length()));
        bufferHeader.pre = pre;
        bufferHeader.bufferLength = bufferStr.length();
        bufferHeader.totalLength = 2 + stringSize(bufferStr.length());
        return bufferHeader;
    }

    private static Buffer generateBuffer(String bufferStr) {
        BufferHeader bufferHeader = generateBufferHeader(bufferStr);
        Buffer buffer = new Buffer();
        buffer.bufferHeader = bufferHeader;
        buffer.content = bufferStr;
        buffer.totalLength = bufferHeader.totalLength + bufferStr.length();
        return buffer;
    }

    private static Buffer getBufferHeader(StringBuffer stringBuffer) {
        BufferHeader bufferHeader = null;
        Buffer buffer = null;
        char[] pre = new char[2];
        if (stringBuffer.length() == 0) {
            return null;
        }
        stringBuffer.getChars(0, 2, pre, 0);
        if (pre[0] == '#' && pre[1] > '0' && pre[1] <= '9') {
            bufferHeader = new BufferHeader();
            bufferHeader.pre = pre;
            int stringSize = Integer.valueOf(pre[1] - '0');
            char[] bufferLengthArr = new char[stringSize];
            stringBuffer.getChars(2, 2 + stringSize, bufferLengthArr, 0);
            bufferHeader.bufferLength = Integer.valueOf(String.valueOf(bufferLengthArr));
            char[] content = new char[bufferHeader.bufferLength];
            stringBuffer.getChars(2 + stringSize, 2 + stringSize + bufferHeader.bufferLength, content, 0);
            buffer = new Buffer();
            buffer.bufferHeader = bufferHeader;
            buffer.content = String.valueOf(content);
            buffer.totalLength = 2 + stringSize + bufferHeader.bufferLength;
        }
        return buffer;
    }

    private static int stringSize(int x) {
        for (int i = 0; ; i++)
            if (x <= sizeTable[i])
                return i + 1;
    }

    public boolean tryToAdd(String bufferStr) {
        if (bufferStr.isEmpty()) {
            return true;
        }
        Buffer buffer = generateBuffer(bufferStr);
        if (stringBuffer.capacity() - stringBuffer.length() < buffer.totalLength) {
            isSending = true;
            return false;
        }
        addBuffer(buffer);
        return true;
    }

    public String getFirstBuffer() {
        Buffer buffer = getBufferHeader(this.stringBuffer);
        if (buffer == null) {
            return null;
        }
        this.stringBuffer.delete(0, buffer.totalLength);
        return buffer.content;
    }

    private void addBuffer(Buffer buffer) {
        stringBuffer.append(buffer.bufferHeader.pre);
        stringBuffer.append(buffer.bufferHeader.bufferLength);
        stringBuffer.append(buffer.content);
    }

    public boolean isSending() {
        return isSending;
    }

    public void setSending(boolean sending) {
        isSending = sending;
    }

    public static class BufferHeader {
        public char[] pre;
        public int bufferLength;
        public int totalLength;
        public BufferHeader() {
        }
    }

    public static class Buffer {
        public BufferHeader bufferHeader;
        public String content;
        public int totalLength;
        public Buffer() {
        }
    }
}
