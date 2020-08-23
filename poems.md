---
title: Poemas
layout: post
---

<section class="posts">
        {% for post in site.categories.poem %}
        <div class="poem">
          <a href="{{site.baseurl}}{{post.url}}"><h3>{{post.title}}</h3></a>
          <small>{{post.date|date_to_string}}</small>
		            <p>
            {{post.content}}
          </p>
        </div>
        {% endfor %}
      </section>
