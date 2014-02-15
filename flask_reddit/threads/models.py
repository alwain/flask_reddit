# -*- coding: utf-8 -*-
"""
All database abstractions for threads and comments
go in this file.
"""
from flask_reddit import db
from flask_reddit.threads import constants as THREAD
from flask_reddit import utils
import datetime

thread_upvotes = db.Table('thread_upvotes',
    db.Column('user_id', db.Integer, db.ForeignKey('users_user.id')),
    db.Column('thread_id', db.Integer, db.ForeignKey('threads_thread.id'))
)

comment_upvotes = db.Table('comment_upvotes',
    db.Column('user_id', db.Integer, db.ForeignKey('users_user.id')),
    db.Column('comment_id', db.Integer, db.ForeignKey('threads_comment.id'))
)

class Thread(db.Model):
    """
    We will mimic reddit, with votable threads. Each thread may have either
    a body text or a link, but not both.
    """
    __tablename__ = 'threads_thread'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(THREAD.MAX_TITLE))
    text = db.Column(db.String(THREAD.MAX_BODY), default=None)
    link = db.Column(db.String(THREAD.MAX_LINK), default=None)
    thumbnail = db.Column(db.String(THREAD.MAX_LINK), default=None)

    user_id = db.Column(db.Integer, db.ForeignKey('users_user.id'))

    created_on = db.Column(db.DateTime, default=db.func.now())
    updated_on = db.Column(db.DateTime, default=db.func.now(), onupdate=db.func.now())
    comments = db.relationship('Comment', backref='thread', lazy='dynamic')

    status = db.Column(db.SmallInteger, default=THREAD.ALIVE)

    votes = db.Column(db.Integer, default=1)

    def __init__(self, title, text, link, user_id):
        self.title = title
        self.text = text
        self.link = link
        self.user_id = user_id

    def __repr__(self):
        return '<Thread %r>' % (self.title)

    def get_comments(self, order_by='timestamp'):
        """
        default order by timestamp
        return only top levels!
        """
        if order_by == 'timestamp':
            return self.comments.filter_by(depth=1).\
                order_by(db.desc(Comment.created_on)).all()[:THREAD.MAX_COMMENTS]
        else:
            return self.comments.filter_by(depth=1).\
                order_by(db.desc(Comment.created_on)).all()[:THREAD.MAX_COMMENTS]

    def get_status(self):
        """
        returns string form of status, 0 = 'dead', 1 = 'alive'
        """
        return THREAD.STATUS[self.status]

    def get_age(self):
        """
        returns the raw age of this thread in seconds
        """
        return (self.created_on - datetime.datetime(1970, 1, 1)).total_seconds()

    def pretty_date(self, typeof='created'):
        """
        returns a humanized version of the raw age of this thread,
        eg: 34 minutes ago versus 2040 seconds ago.
        """
        if typeof == 'created':
            return utils.pretty_date(self.created_on)
        elif typeof == 'updated':
            return utils.pretty_date(self.updated_on)

    def add_comment(self, comment_text, comment_parent_id, user_id):
        """
        add a comment to this particular thread
        """
        if len(comment_parent_id) > 0:
            # parent_comment = Comment.query.get_or_404(comment_parent_id)
            # if parent_comment.depth + 1 > THREAD.MAX_COMMENT_DEPTH:
            #    flash('You have exceeded the maximum comment depth')
            comment_parent_id = int(comment_parent_id)
            comment = Comment(thread_id=self.id, user_id=user_id,
                    text=comment_text, parent_id=comment_parent_id)
        else:
            comment = Comment(thread_id=self.id, user_id=user_id,
                    text=comment_text)

        db.session.add(comment)
        db.session.commit()
        comment.set_depth()
        return comment

    def get_voter_ids(self):
        """
        return ids of users who voted this thread up
        """
        select = thread_upvotes.select(thread_upvotes.c.thread_id==self.id)
        rs = db.engine.execute(select)
        ids = rs.fetchall() # list of tuples
        return ids

    def vote(self, user_id):
        """
        allow a user to vote on a thread
        """
        db.engine.execute(
            thread_upvotes.insert(),
            user_id   = int(user_id),
            thread_id = self.id
        )
        self.votes = self.votes + 1
        db.session.commit()

    def extract_thumbnail(self):
        """
        use reddit algorithm to extract thumbnail from link, grayscale it
        """
        pass

class Comment(db.Model):
    """
    This class is here because comments can only be made on threads,
    so it is contained completly in the threads module.

    Note the parent_id and children values. A comment can be commented
    on, so a comment has a one to many relationship with itself.

    Backrefs:
        A comment can refer to its parent thread with 'thread'
        A comment can refer to its parent comment (if exists) with 'parent'
    """
    __tablename__ = 'threads_comment'
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String(THREAD.MAX_BODY), default=None)

    user_id = db.Column(db.Integer, db.ForeignKey('users_user.id'))
    thread_id = db.Column(db.Integer, db.ForeignKey('threads_thread.id'))

    parent_id = db.Column(db.Integer, db.ForeignKey('threads_comment.id'))
    children = db.relationship('Comment', backref=db.backref('parent',
            remote_side=[id]), lazy='dynamic')

    depth = db.Column(db.Integer, default=1) # start at depth 1

    created_on = db.Column(db.DateTime, default=db.func.now())
    updated_on = db.Column(db.DateTime, default=db.func.now(), onupdate=db.func.now())

    votes = db.Column(db.Integer, default=1)

    def __repr__(self):
        return '<Comment %r>' % (self.text[:25])

    def __init__(self, thread_id, user_id, text, parent_id=None):
        self.thread_id = thread_id
        self.user_id = user_id
        self.text = text
        self.parent_id = parent_id

    def set_depth(self):
        """
        call after initializing
        """
        if self.parent:
            self.depth = self.parent.depth + 1
            db.session.commit()

    def get_comments(self, order_by='timestamp'):
        """
        default order by timestamp
        """
        if order_by == 'timestamp':
            return self.children.order_by(db.desc(Comment.created_on)).all()[:THREAD.MAX_COMMENTS]
        else:
            return self.comments.order_by(db.desc(Comment.created_on)).all()[:THREAD.MAX_COMMENTS]

    def get_margin_left(self):
        """
        nested comments are pushed right on a page
        -15px is our default margin for top level comments
        """
        margin_left = 15 + ((self.depth-1) * 32)
        margin_left = min(margin_left, 680)
        return str(margin_left) + "px"

    def get_age(self):
        """
        returns the raw age of this thread in seconds
        """
        return (self.created_on - datetime.datetime(1970,1,1)).total_seconds()

    def pretty_date(self, typeof='created'):
        """
        returns a humanized version of the raw age of this thread,
        eg: 34 minutes ago versus 2040 seconds ago.
        """
        if typeof == 'created':
            return utils.pretty_date(self.created_on)
        elif typeof == 'updated':
            return utils.pretty_date(self.updated_on)

    def vote(self, direction):
        """
        """
        pass

    def comment_on(self):
        """
        when someone comments on this particular comment
        """
        pass
