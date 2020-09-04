---
title: Journal
layout: post
---

<section class="posts">
        {% for post in site.tags.journal %}
        <div class="journal">
          <a href="{{site.baseurl}}{{post.url}}"><h3>{{post.title}}</h3></a>
		            <p>
            {{post.content}}
          </p>
        </div>
        {% endfor %}
      </section>
