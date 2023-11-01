package com.insightfinder.kubeactions.controller;

import com.insightfinder.kubeactions.config.IFConfig;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;
import org.springframework.web.servlet.ModelAndView;

@Component
public class HeaderHandlerInterceptor implements HandlerInterceptor {
    @Autowired
    private IFConfig ifConfig;
    @Override
    public void afterCompletion(HttpServletRequest request, HttpServletResponse response, Object object, Exception arg3) throws Exception {
    }

    @Override
    public void postHandle(HttpServletRequest request, HttpServletResponse response, Object object, ModelAndView model) throws Exception {
    }

    @Override
    public boolean preHandle(HttpServletRequest request,
                             HttpServletResponse response, Object handler) throws Exception {
        String serverid = request.getHeader("serverid");
        if (serverid != null && serverid.length() > 0) {
            return serverid.equalsIgnoreCase(ifConfig.getActionServerId());
        }
        return false;
    }
}
